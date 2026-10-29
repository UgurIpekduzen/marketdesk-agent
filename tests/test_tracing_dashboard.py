"""Tests for src/tracing_dashboard.py: reading the traces and counting errors.

No network: Langfuse is a stand-in that answers pages of observations.
"""

import base64
import http.server
import io
import json
import pickle
import threading
import urllib.error
import urllib.request

import pytest

from scripts import trace_dashboard
from src import messages, messages_en, tracing_dashboard
from src.tracing_dashboard import (
    DashboardUnavailable,
    ErrorCount,
    count_errors,
    credentials,
    fetch_observations,
    render_html,
    render_table,
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


def test_messages_and_tools_are_counted_apart_and_ranked():
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


def test_an_observation_without_an_error_is_not_counted():
    observations = [span("message"), span("FunctionTool.acall"), {"name": "x"}]

    assert count_errors(observations) == []


def test_the_same_kind_in_a_message_and_in_a_tool_is_two_rows():
    observations = [
        span("message", "NOT_FOUND"),
        span("FunctionTool.acall", "NOT_FOUND"),
    ]

    rows = count_errors(observations)

    assert {(row.kind, row.where) for row in rows} == {
        ("NOT_FOUND", "message"),
        ("NOT_FOUND", "tool"),
    }


def test_pages_are_read_by_cursor_until_there_is_none():
    langfuse = FakeLangfuse(
        {"data": [span("message", "A")], "meta": {"cursor": "next"}},
        {"data": [span("message", "B")], "meta": {}},
    )

    found = fetch_observations("pk", "sk", 100, "https://x.test", langfuse)

    assert [o["metadata"][ERROR] for o in found] == ["A", "B"]
    assert len(langfuse.requests) == 2
    assert "cursor=" not in langfuse.requests[0].full_url
    assert "cursor=next" in langfuse.requests[1].full_url


def test_the_request_asks_for_metadata_and_no_clock_time():
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


def test_reading_stops_at_the_number_asked_for_even_if_pages_go_on():
    calls = []

    def endless(request, timeout=None):
        calls.append(request)
        return Page({"data": [span("message")] * 100, "meta": {"cursor": "again"}})

    found = fetch_observations("pk", "sk", 250, "https://x.test", endless)

    assert len(found) == 250
    assert len(calls) == 3


def test_a_refused_request_gives_the_status_and_not_the_answer():
    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "secret sk-2 was wrong", {}, io.BytesIO(b"sk-2")
        )

    with pytest.raises(DashboardUnavailable) as raised:
        fetch_observations("pk", "sk-2", 10, "https://x.test", refuse)

    assert raised.value.code == "REQUEST_FAILED"
    assert raised.value.status == 401
    assert "sk-2" not in str(raised.value)


def test_a_service_that_cannot_be_reached_is_told_apart():
    def down(request, timeout=None):
        raise urllib.error.URLError("no route to host")

    with pytest.raises(DashboardUnavailable) as raised:
        fetch_observations("pk", "sk", 10, "https://x.test", down)

    assert raised.value.code == "UNREACHABLE"


def test_keys_are_read_from_the_environment_or_the_page_says_they_are_missing():
    assert credentials({"LANGFUSE_PUBLIC_KEY": "a", "LANGFUSE_SECRET_KEY": "b"}) == (
        "a",
        "b",
    )
    for environment in ({}, {"LANGFUSE_PUBLIC_KEY": "a"}, {"LANGFUSE_SECRET_KEY": "b"}):
        with pytest.raises(DashboardUnavailable) as raised:
            credentials(environment)
        assert raised.value.code == "KEYS_MISSING"


# --- The page, the table and the command ---------------------------------

ROWS = [
    ErrorCount("TOOL_LIMIT", "tool", 8),
    ErrorCount("ROUTER_REFUSED", "message", 3),
    ErrorCount("NOT_FOUND", "message", 1),
    ErrorCount("NOT_FOUND", "tool", 1),
]


def test_the_page_shows_every_kind_with_its_count_and_in_the_chosen_language():
    page = render_html(ROWS, 342, messages_en, "en")

    assert page.startswith('<!doctype html><html lang="en">')
    for kind in ("TOOL_LIMIT", "ROUTER_REFUSED", "NOT_FOUND"):
        assert kind in page
    assert messages_en.DASH_TITLE in page and "342" in page
    assert messages.DASH_TITLE not in page


def test_a_kind_in_a_message_and_in_a_tool_is_one_bar_with_two_parts():
    page = render_html(ROWS, 10, messages_en, "en")

    svg = page[page.index("<svg") : page.index("</svg>")]
    assert svg.count(">NOT_FOUND</text>") == 1
    assert ">2</text>" in svg


def test_the_page_is_one_file_without_scripts_or_outside_addresses():
    page = render_html(ROWS, 10, messages_en, "en")

    assert "<script" not in page
    assert "http://" not in page and "https://" not in page


def test_what_comes_from_the_traces_is_escaped_in_the_page():
    rows = [ErrorCount("<img src=x onerror=alert(1)>", "tool", 1)]

    page = render_html(rows, 1, messages_en, "en")

    assert "<img" not in page
    assert "&lt;img" in page


def test_without_errors_the_page_says_so_and_draws_no_chart():
    page = render_html([], 5, messages_en, "en")

    assert messages_en.DASH_NO_ERRORS in page
    assert "<svg" not in page


def test_the_table_lists_the_counts_for_the_terminal():
    table = render_table(ROWS, 342, messages_en)

    lines = table.splitlines()
    assert "342" in lines[0] and "11" not in lines[0]
    assert lines[1].split() == ["TOOL_LIMIT", "tool", "8"]
    assert len(lines) == 1 + len(ROWS)


def test_the_command_writes_the_page_and_prints_the_table(
    monkeypatch, tmp_path, capsys
):
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


def test_the_command_says_why_it_cannot_read_and_writes_nothing(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    output = tmp_path / "page.html"

    code = trace_dashboard.main(["--lang", "en", "--output", str(output)])

    assert code == 1
    assert not output.exists()
    assert messages_en.DASH_KEYS_MISSING in capsys.readouterr().err


def test_a_failure_keeps_its_status_when_it_is_pickled_for_the_cache():
    failure = DashboardUnavailable("REQUEST_FAILED", 401)

    kept = pickle.loads(pickle.dumps(failure))

    assert (kept.code, kept.status) == ("REQUEST_FAILED", 401)


# --- The keys stay on the address they were meant for ----------------------


def test_a_plain_address_is_refused_before_anything_is_sent():
    sent = []

    def opener(request, timeout=None):
        sent.append(request)
        return Page({"data": [], "meta": {}})

    with pytest.raises(DashboardUnavailable) as raised:
        fetch_observations("pk", "sk", 10, "http://x.test", opener)

    assert raised.value.code == "INSECURE_URL"
    assert sent == []


def test_the_message_for_a_plain_address_says_https_in_both_languages():
    failure = DashboardUnavailable("INSECURE_URL")

    assert "https://" in tracing_dashboard.failure_text(messages, failure)
    assert "https://" in tracing_dashboard.failure_text(messages_en, failure)


def test_a_redirect_is_not_followed_so_the_keys_do_not_travel_on():
    reached = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            reached.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    target = http.server.HTTPServer(("127.0.0.1", 0), Target)

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target.server_port}/")
            self.end_headers()

        def log_message(self, *args):
            pass

    redirector = http.server.HTTPServer(("127.0.0.1", 0), Redirector)
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
    assert reached == []
