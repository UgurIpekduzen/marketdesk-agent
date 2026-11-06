"""Tests for src/tracing_dashboard.py: reading the traces and counting errors.

No network: Langfuse is a stand-in that answers pages of observations.
"""

import ast
import base64
import functools
import http.server
import io
import json
import pickle
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from scripts import trace_dashboard
from src import messages, messages_en, tracing_dashboard
from src.tracing_dashboard import (
    DashboardUnavailableError,
    ErrorCount,
    count_errors,
    credentials,
    fetch_observations,
    kinds_by_total,
    render_html,
    render_table,
    vega_chart,
)

ERROR = tracing_dashboard.ERROR_KEY


def span(name, error=None):
    metadata = {"attributes.marketdesk.intent": "support"}
    if error:
        metadata[ERROR] = error
    return {"name": name, "metadata": metadata}


class Page:
    """What urlopen returns: usable in a with block, holds one JSON body."""

    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *details):
        return False


class FakeLangfuse:
    """Answers the pages in turn and keeps the requests it was asked."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        return Page(self.pages.pop(0))


def test_messages_tools_counted_apart():
    observations = [
        span("message", "ROUTER_REFUSED"),
        span("message", "ROUTER_REFUSED"),
        span("FunctionTool.acall", "TOOL_LIMIT"),
        span("FunctionTool.acall", "TOOL_LIMIT"),
        span("FunctionTool.acall", "TOOL_LIMIT"),
        span("message", "STEP_LIMIT"),
    ]

    assert count_errors(observations) == [
        ErrorCount("TOOL_LIMIT", "tool", 3),
        ErrorCount("ROUTER_REFUSED", "message", 2),
        ErrorCount("STEP_LIMIT", "message", 1),
    ]


def test_clean_observation_not_counted():
    observations = [span("message"), span("FunctionTool.acall"), {"name": "x"}]

    assert count_errors(observations) == []


def test_same_kind_twice_is_two_rows():
    observations = [
        span("message", "NOT_FOUND"),
        span("FunctionTool.acall", "NOT_FOUND"),
    ]

    rows = count_errors(observations)

    assert {(row.kind, row.where) for row in rows} == {
        ("NOT_FOUND", "message"),
        ("NOT_FOUND", "tool"),
    }


def test_pages_are_read_by_cursor():
    langfuse = FakeLangfuse(
        {"data": [span("message", "A")], "meta": {"cursor": "next"}},
        {"data": [span("message", "B")], "meta": {}},
    )

    found = fetch_observations("pk", "sk", 100, "https://x.test", langfuse)

    assert [o["metadata"][ERROR] for o in found] == ["A", "B"]
    assert len(langfuse.requests) == 2
    assert "cursor=" not in langfuse.requests[0].full_url
    assert "cursor=next" in langfuse.requests[1].full_url


def test_request_asks_for_metadata():
    langfuse = FakeLangfuse({"data": [], "meta": {}})

    fetch_observations("pk", "sk", 10, "https://x.test/", langfuse)

    url = langfuse.requests[0].full_url
    assert url.startswith("https://x.test/api/public/v2/observations?")
    assert "fields=core%2Cbasic%2Cmetadata" in url
    assert "fromStartTime" not in url


def test_the_keys_go_in_one_header_only():
    langfuse = FakeLangfuse({"data": [], "meta": {}})

    fetch_observations("pk-1", "sk-2", 10, "https://x.test", langfuse)

    request = langfuse.requests[0]
    signed = base64.b64encode(b"pk-1:sk-2").decode()
    assert request.get_header("Authorization") == f"Basic {signed}"
    assert "pk-1" not in request.full_url and "sk-2" not in request.full_url


def endless_of_reading_stops_at_the_limit(calls, request, timeout=None):
    calls.append(request)
    return Page({"data": [span("message")] * 100, "meta": {"cursor": "again"}})


def test_reading_stops_at_the_limit():
    calls = []

    found = fetch_observations(
        "pk",
        "sk",
        250,
        "https://x.test",
        functools.partial(endless_of_reading_stops_at_the_limit, calls),
    )

    assert len(found) == 250
    assert len(calls) == 3


def refuse_of_refusal_gives_status_only(request, timeout=None):
    raise urllib.error.HTTPError(
        request.full_url, 401, "secret sk-2 was wrong", {}, io.BytesIO(b"sk-2")
    )


def test_refusal_gives_status_only():

    with pytest.raises(DashboardUnavailableError) as raised:
        fetch_observations(
            "pk", "sk-2", 10, "https://x.test", refuse_of_refusal_gives_status_only
        )

    assert raised.value.code == "REQUEST_FAILED"
    assert raised.value.status == 401
    assert "sk-2" not in str(raised.value)


def down_of_unreachable_is_told_apart(request, timeout=None):
    raise urllib.error.URLError("no route to host")


def test_unreachable_is_told_apart():

    with pytest.raises(DashboardUnavailableError) as raised:
        fetch_observations(
            "pk", "sk", 10, "https://x.test", down_of_unreachable_is_told_apart
        )

    assert raised.value.code == "UNREACHABLE"


def test_keys_come_from_environment():
    assert credentials({"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b"}) == (
        "a",
        "b",
    )
    for environment in ({}, {"LANGFUSE_PUBLIC_KEY": "a"}, {"LANGFUSE_SECRET_KEY": "b"}):
        with pytest.raises(DashboardUnavailableError) as raised:
            credentials(environment)
        assert raised.value.code == "KEYS_MISSING"


# --- The page, the table and the command ---------------------------------

ROWS = [
    ErrorCount("TOOL_LIMIT", "tool", 8),
    ErrorCount("ROUTER_REFUSED", "message", 3),
    ErrorCount("NOT_FOUND", "message", 1),
    ErrorCount("NOT_FOUND", "tool", 1),
]


def test_page_shows_kinds_and_counts():
    page = render_html(ROWS, 342, messages_en, "en")

    assert page.startswith('<!doctype html><html lang="en">')
    for kind in ("TOOL_LIMIT", "ROUTER_REFUSED", "NOT_FOUND"):
        assert kind in page
    assert messages_en.DASH_TITLE in page and "342" in page
    assert messages.DASH_TITLE not in page


def test_one_bar_with_two_parts():
    page = render_html(ROWS, 10, messages_en, "en")

    svg = page[page.index("<svg") : page.index("</svg>")]
    assert svg.count(f">{messages_en.DASH_ERROR_LABELS['NOT_FOUND']}</text>") == 1
    assert ">2</text>" in svg


def test_page_has_no_script_or_url():
    page = render_html(ROWS, 10, messages_en, "en")

    assert "<script" not in page
    assert "http://" not in page and "https://" not in page


def test_trace_text_is_escaped():
    rows = [ErrorCount("<img src=x onerror=alert(1)>", "tool", 1)]

    page = render_html(rows, 1, messages_en, "en")

    assert "<img" not in page
    assert "&lt;img" in page


def test_no_errors_no_chart():
    page = render_html([], 5, messages_en, "en")

    assert messages_en.DASH_NO_ERRORS in page
    assert "<svg" not in page


def test_terminal_table_has_counts():
    table = render_table(ROWS, 342, messages_en)

    lines = table.splitlines()
    assert "342" in lines[0] and "11" not in lines[0]
    label = messages_en.DASH_ERROR_LABELS["TOOL_LIMIT"]
    assert lines[1].startswith(label)
    assert lines[1].split()[-3:] == ["TOOL_LIMIT", "tool", "8"]
    assert len(lines) == 1 + len(ROWS)


def test_command_writes_page_and_table(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        tracing_dashboard,
        "fetch_observations",
        lambda public, secret, newest: [span("message", "STEP_LIMIT")],
    )
    output = tmp_path / "out" / "page.html"

    code = trace_dashboard.main(["--lang", "en", "--output", str(output)])

    assert code == 0
    assert "STEP_LIMIT" in output.read_text(encoding="utf-8")
    shown = capsys.readouterr().out
    assert "STEP_LIMIT" in shown and str(output) in shown


def test_command_failure_writes_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    output = tmp_path / "page.html"

    code = trace_dashboard.main(["--lang", "en", "--output", str(output)])

    assert code == 1
    assert not output.exists()
    assert messages_en.DASH_KEYS_MISSING in capsys.readouterr().err


def test_failure_survives_pickling():
    failure = DashboardUnavailableError("REQUEST_FAILED", 401)

    kept = pickle.loads(pickle.dumps(failure))

    assert (kept.code, kept.status) == ("REQUEST_FAILED", 401)


# --- The keys stay on the address they were meant for ----------------------


def opener_of_http_is_refused_unsent(sent, request, timeout=None):
    sent.append(request)
    return Page({"data": [], "meta": {}})


def test_http_is_refused_unsent():
    sent = []

    with pytest.raises(DashboardUnavailableError) as raised:
        fetch_observations(
            "pk",
            "sk",
            10,
            "http://x.test",
            functools.partial(opener_of_http_is_refused_unsent, sent),
        )

    assert raised.value.code == "INSECURE_URL"
    assert sent == []


def test_https_message_in_both_languages():
    failure = DashboardUnavailableError("INSECURE_URL")

    assert "https://" in tracing_dashboard.failure_text(messages, failure)
    assert "https://" in tracing_dashboard.failure_text(messages_en, failure)


class TargetHandler(http.server.BaseHTTPRequestHandler):
    """The server a redirect points to; its server keeps the Authorization it saw."""

    def do_GET(self):
        self.server.reached.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


class RedirectHandler(http.server.BaseHTTPRequestHandler):
    """Answers every request with a redirect to the target's port."""

    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:{self.server.target_port}/")
        self.end_headers()

    def log_message(self, *args):
        pass


def test_redirect_is_not_followed():
    target = http.server.HTTPServer(("127.0.0.1", 0), TargetHandler)
    target.reached = []
    redirector = http.server.HTTPServer(("127.0.0.1", 0), RedirectHandler)
    redirector.target_port = target.server_port
    for server in (target, redirector):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{redirector.server_port}/",
        headers={"Authorization": "Basic secret"},
    )

    try:
        with pytest.raises(urllib.error.HTTPError) as raised:
            tracing_dashboard.OPENER.open(request, timeout=5)
    finally:
        target.shutdown()
        redirector.shutdown()

    assert raised.value.code == 302
    assert target.reached == []


def test_kinds_ordered_by_total():
    rows = [
        ErrorCount("NOT_FOUND", "message", 1),
        ErrorCount("NOT_FOUND", "tool", 3),
        ErrorCount("STEP_LIMIT", "message", 2),
        ErrorCount("TOOL_LIMIT", "tool", 8),
        ErrorCount("A_KIND", "tool", 2),
    ]

    ordered = kinds_by_total(rows)

    assert [kind for kind, _ in ordered] == [
        "TOOL_LIMIT",
        "NOT_FOUND",
        "A_KIND",
        "STEP_LIMIT",
    ]
    assert ordered[1][1] == {"message": 1, "tool": 3}


def test_parts_share_colours_with_page():
    assert set(tracing_dashboard.WHERE_ORDER) == set(tracing_dashboard.WHERE_COLOURS)
    page = render_html(ROWS, 10, messages_en, "en")
    assert "--message: #5b9bd8" in page and "--tool: #e8a24a" in page


def test_app_chart_order_and_colours():
    data, spec = vega_chart(ROWS, messages_en)

    in_words = [messages_en.DASH_ERROR_LABELS[kind] for kind, _ in kinds_by_total(ROWS)]
    assert spec["encoding"]["y"]["sort"] == in_words
    assert {row["kind"] for row in data} <= set(in_words)
    scale = spec["encoding"]["color"]["scale"]
    assert scale["domain"] == ["message", "tool"]
    assert scale["range"] == [
        tracing_dashboard.WHERE_COLOURS["message"],
        tracing_dashboard.WHERE_COLOURS["tool"],
    ]
    # One entry for each part that has a count: NOT_FOUND has both, the rest one.
    assert {(row["kind"], row["where"]): row["count"] for row in data} == {
        (messages_en.DASH_ERROR_LABELS["TOOL_LIMIT"], "tool"): 8,
        (messages_en.DASH_ERROR_LABELS["ROUTER_REFUSED"], "message"): 3,
        (messages_en.DASH_ERROR_LABELS["NOT_FOUND"], "message"): 1,
        (messages_en.DASH_ERROR_LABELS["NOT_FOUND"], "tool"): 1,
    }


def test_chart_label_room_whole_ticks():
    _, spec = vega_chart(ROWS, messages_en)

    longest = max(len(row.kind) for row in ROWS)
    # About 8 pixels a letter at the size of the axis labels.
    assert tracing_dashboard.LABEL_LIMIT >= longest * 8
    assert spec["encoding"]["y"]["axis"]["labelLimit"] == tracing_dashboard.LABEL_LIMIT
    assert spec["encoding"]["x"]["axis"]["tickMinStep"] == 1


def test_axes_named_in_page_language():
    _, spec_tr = vega_chart(ROWS, messages)
    _, spec_en = vega_chart(ROWS, messages_en)

    assert spec_tr["encoding"]["y"]["axis"]["title"] == messages.DASH_COLUMN_KIND
    assert spec_en["encoding"]["x"]["axis"]["title"] == messages_en.DASH_COLUMN_COUNT
    assert spec_tr["encoding"]["color"]["scale"]["domain"] == ["ileti", "araç"]


# --- The kinds in words ----------------------------------------------------


def codes_the_code_can_emit() -> set[str]:
    """Every error code that tools and failures can put on a span, in the code."""
    root = Path(__file__).resolve().parent.parent / "src"
    codes = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                if name == "error" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        codes.add(first.value)
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "error"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        codes.add(value.value)
    return {code for code in codes if code.isupper() and " " not in code}


def test_emitted_codes_have_words():
    from src import failures, orchestrator

    emitted = codes_the_code_can_emit() | {
        failures.QUOTA_EXCEEDED,
        failures.PROVIDER_BUSY,
        failures.KEY_REFUSED,
        failures.KEY_NOT_SET,
        failures.DAILY_BUDGET,
        failures.RUN_FAILED,
        orchestrator.ROUTER_REFUSED,
        "STEP_LIMIT",
    }

    assert emitted
    assert emitted <= set(messages.DASH_ERROR_LABELS)
    assert emitted <= set(messages_en.DASH_ERROR_LABELS)


def test_words_are_unique_and_fit():
    for catalog in (messages, messages_en):
        words = list(catalog.DASH_ERROR_LABELS.values())
        assert len(set(words)) == len(words)
        # About 8 pixels a letter at the size of the axis labels.
        assert max(len(word) for word in words) * 8 <= tracing_dashboard.LABEL_LIMIT


def test_unworded_kind_shows_code():
    assert tracing_dashboard.kind_label(messages_en, "A_NEW_KIND") == "A_NEW_KIND"
    assert tracing_dashboard.kind_label(messages_en, "NOT_FOUND") == "Order not found"
    assert tracing_dashboard.kind_label(messages, "NOT_FOUND") == "Sipariş bulunamadı"


def test_page_shows_words_and_codes():
    rows = [ErrorCount("TOOL_LIMIT", "tool", 8), ErrorCount("A_NEW_KIND", "tool", 1)]

    page = render_html(rows, 9, messages_en, "en")

    assert "Tool call limit exceeded" in page
    assert "<code>TOOL_LIMIT</code>" in page
    assert "<code>A_NEW_KIND</code>" in page


def test_decision_codes_have_words():
    from src.rules.returns import DecisionCode

    # create_return_request answers an error with the decision's own code when
    # the refund is zero; ELIGIBLE has a refund, so it never comes out as one.
    codes = {code.value for code in DecisionCode} - {DecisionCode.ELIGIBLE.value}

    assert codes <= set(messages.DASH_ERROR_LABELS)
    assert codes <= set(messages_en.DASH_ERROR_LABELS)


def test_runtime_codes_are_known():
    """The scan of the emitted codes reads only codes written out in the source.

    These are the places where an error code is not written out: a helper that
    takes the code, a decision's code, the span's copy of a tool's error. A new
    place breaks this test, and its codes need words in both catalogs (and a
    line in the test above, if they are not literal).
    """
    root = Path(__file__).resolve().parent.parent / "src"
    found = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "error"
                        and not isinstance(value, ast.Constant)
                    ):
                        found.add((path.name, ast.unparse(value)))
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", getattr(node.func, "attr", "")) == "error"
                and node.args
                and not isinstance(node.args[0], ast.Constant)
            ):
                found.add((path.name, "error(" + ast.unparse(node.args[0]) + ")"))

    assert found == {
        ("review_corpus.py", "code"),
        ("review_themes.py", "code"),
        ("semantic_layer.py", "code"),
        ("return_requests.py", "decision.code.value"),
        ("tracing.py", "result.get('error')"),
    }
