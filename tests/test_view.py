"""Tests for what the page shows of an answer."""

import pytest

from src import messages
from src.agents.ops import Reply as OpsReply
from src.agents.run_log import RunLog
from src.agents.support import Reply as SupportReply
from src.orchestrator import Answer, Intent
from src.ui.session_pool import SessionLimitReached
from src.ui.view import approval_card, friendly_error, view_of, without_images

PENDING = {
    "pending": True,
    "order": "SIP-1",
    "reason": "damaged",
    "refund_amount": "115.00",
    "request_status": "PENDING_REVIEW",
}
SECTIONS = {
    "results": [
        {"citation": "İade Politikası, Bölüm 2", "text": "..."},
        {"citation": "İptal Politikası, Bölüm 1", "text": "..."},
    ]
}


def log_with(tools=(), results=(), tokens=(0, 0), llm_calls=1) -> RunLog:
    log = RunLog()
    log.llm_calls = llm_calls
    log.input_tokens, log.output_tokens = tokens
    for name in tools:
        log.add_tool_call(name, {})
    log.tool_results.extend(results)
    return log


def router_log() -> RunLog:
    return log_with(tokens=(200, 1))


def test_support_answer_shows_agent_tools_steps_and_tokens():
    log = log_with(["get_order_status"], tokens=(2000, 50), llm_calls=2)
    answer = Answer(
        Intent.SUPPORT, "x", SupportReply("Teslim edildi.", log), router_log()
    )

    view = view_of(answer)

    assert view.text == "Teslim edildi."
    assert view.agent == messages.UI_AGENT_SUPPORT
    assert view.tools == ["get_order_status"]
    # One classification call, two model calls and one tool call.
    assert view.steps == 4
    assert view.tokens == 2251
    assert view.pending is None
    assert view.table is None


def test_pending_request_is_carried_to_the_page():
    reply = SupportReply("Onayınız istenecek.", log_with(), PENDING)

    view = view_of(Answer(Intent.SUPPORT, "x", reply, router_log()))

    assert view.pending == PENDING


def test_only_the_sections_the_answer_names_are_sources():
    log = log_with(["search_policies"], [("search_policies", SECTIONS)])
    reply = SupportReply("14 gün içinde (İade Politikası, Bölüm 2).", log)

    view = view_of(Answer(Intent.SUPPORT, "x", reply, router_log()))

    assert view.sources == ["İade Politikası, Bölüm 2"]


def test_ops_answer_shows_table_sql_and_caveat_apart_from_the_text():
    result = {"columns": ["state", "rate"], "rows": [["SP", 0.03]], "sql": "SELECT 1"}
    log = log_with(
        ["run_metric"], [("list_metrics", {"metrics": []}), ("run_metric", result)]
    )
    reply = OpsReply("SP: %3.", log, queries=["SELECT 1"], caveats=["Gözlemsel."])

    view = view_of(Answer(Intent.OPS_METRIC, reply.display, reply, router_log()))

    assert view.text == "SP: %3."
    assert view.agent == messages.UI_AGENT_OPS
    assert view.table == {"columns": ["state", "rate"], "rows": [["SP", 0.03]]}
    assert view.queries == ["SELECT 1"]
    assert view.queries_heading == messages.OPS_USED_SQL_HEADING
    assert view.caveats == ["Gözlemsel."]


def test_ops_answer_that_gave_up_shows_the_tried_sql_and_no_table():
    result = {"columns": ["n"], "rows": [[1]], "sql": "SELECT 1"}
    log = log_with(["run_sql"], [("run_sql", result)])
    reply = OpsReply(messages.SQL_GAVE_UP, log, queries=["SELEC 1"], gave_up=True)

    view = view_of(Answer(Intent.OPS_METRIC, reply.display, reply, router_log()))

    assert view.table is None
    assert view.queries_heading == messages.OPS_TRIED_SQL_HEADING


def test_refused_message_is_shown_as_the_routers_answer():
    answer = Answer(
        Intent.OPS_METRIC, messages.ROUTER_OPS_NOT_ALLOWED, None, router_log()
    )

    view = view_of(answer)

    assert view.text == messages.ROUTER_OPS_NOT_ALLOWED
    assert view.agent == messages.UI_AGENT_ROUTER
    assert view.tools == []
    assert view.steps == 1


def test_approval_card_names_order_reason_amount_and_level():
    card = approval_card({**PENDING, "request_status": "PENDING_SENIOR"})

    assert card == {
        messages.UI_APPROVAL_ORDER: "SIP-1",
        messages.UI_APPROVAL_REASON: "hasarlı ürün",
        messages.UI_APPROVAL_AMOUNT: "115.00 BRL",
        messages.UI_APPROVAL_LEVEL: "kıdemli onay bekliyor",
    }


def wrapped(inner: Exception) -> Exception:
    try:
        raise RuntimeError("workflow failed") from inner
    except RuntimeError as outer:
        return outer


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (
            RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"),
            messages.UI_ERROR_QUOTA,
        ),
        (RuntimeError("503 UNAVAILABLE: high demand"), messages.UI_ERROR_BUSY),
        (wrapped(ValueError("status 429")), messages.UI_ERROR_QUOTA),
        (TimeoutError(), messages.UI_ERROR_TIMEOUT),
        (SessionLimitReached("20 chat sessions are open"), messages.UI_ERROR_FULL),
        (KeyError("GEMINI_API_KEY"), messages.UI_ERROR_NOT_CONFIGURED),
        (ZeroDivisionError("division by zero"), messages.UI_ERROR_GENERIC),
        (RuntimeError("refund of 500.00 BRL failed"), messages.UI_ERROR_GENERIC),
    ],
)
def test_failure_becomes_a_plain_message(failure, message):
    assert friendly_error(failure) == message


def test_failure_details_go_to_the_log_not_to_the_message(caplog):
    with caplog.at_level("ERROR"):
        message = friendly_error(RuntimeError("secret detail at line 42"))

    assert "secret detail" not in message
    assert "secret detail" in caplog.text


@pytest.mark.parametrize(
    "image",
    [
        "![](https://example.com/r.png?veri=SIP-1_122.43)",
        '![logo](https://example.com/logo.png "title")',
        "![x][ref]",
    ],
)
def test_a_markdown_image_in_an_answer_is_not_drawn(image, caplog):
    log = log_with(["get_order_status"])
    answer = Answer(
        Intent.SUPPORT, "x", SupportReply(f"Teslim edildi. {image}", log), router_log()
    )

    with caplog.at_level("WARNING"):
        view = view_of(answer)

    assert view.text == f"Teslim edildi. {messages.UI_IMAGE_REMOVED}"
    assert "example.com" not in view.text
    assert "removed 1 markdown images" in caplog.text


def test_links_and_plain_text_are_left_as_they_are():
    text = "Ayrıntı için [iade politikası](https://example.com/iade) bölüm 2. Not! [a]"

    assert without_images(text) == text
