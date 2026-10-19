"""Tests for what the page shows of an answer."""

import pytest

import config
from src import messages
from src.agents.ops import Reply as OpsReply
from src.agents.run_log import RunLog
from src.agents.support import Reply as SupportReply
from src.formatting import format_number, readable_table
from src.orchestrator import Answer, Intent
from src.ui.chat_session import MessageTooLong
from src.ui.question_limit import QuestionLimitReached
from src.ui.session_pool import SessionLimitReached
from src.ui.view import (
    approval_card,
    friendly_error,
    tools_text,
    unsaid_caveats,
    view_of,
    without_images,
)

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


def test_a_plain_total_shows_turkish_headers_and_no_repeated_numerator():
    table = {
        "columns": ["purchase_month", "numerator", "value"],
        "rows": [["2018-01", 7269, 7269], ["2018-02", 6728, 6728]],
    }

    shown = readable_table(table)

    assert shown["columns"] == ["Ay", "Değer"]
    assert shown["rows"] == [["2018-01", 7269], ["2018-02", 6728]]
    assert shown["numbers"] == {"Değer": True}
    # The answer's own table is left as it was.
    assert table["columns"] == ["purchase_month", "numerator", "value"]


def test_a_ratio_keeps_its_numerator_and_denominator():
    table = {
        "columns": ["customer_state", "numerator", "denominator", "value"],
        "rows": [["SP", 318, 41736, 0.0076]],
    }

    shown = readable_table(table)

    assert shown["columns"] == ["Müşteri eyaleti", "Pay", "Payda", "Değer"]
    assert shown["rows"] == [["SP", 318, 41736, 0.0076]]
    assert shown["numbers"] == {"Pay": True, "Payda": True, "Değer": False}


def test_free_sql_columns_keep_their_names_and_only_numbers_are_numeric():
    table = {
        "columns": ["payment_type", "orders", "share", "active"],
        "rows": [
            ["boleto", 19784, None, True],
            ["voucher", None, 0.04, False],
            ["debit_card", 1527, 0.01, True],
        ],
    }

    shown = readable_table(table)

    assert shown["columns"] == ["payment_type", "orders", "share", "active"]
    # A missing value does not make a column text or its numbers decimals;
    # true/false is not a number.
    assert shown["numbers"] == {"orders": True, "share": False}


def test_the_page_table_shows_turkish_numbers_from_the_library_types():
    # The page hands the numbers over through pandas, which gives numpy
    # types, and turns a whole column with a gap into decimals.
    import pandas as pd

    shown = readable_table(
        {"columns": ["customer_state", "orders"], "rows": [["SP", 41736], ["RJ", None]]}
    )
    frame = pd.DataFrame(shown["rows"], columns=shown["columns"])

    assert str(frame["orders"].dtype) == "float64"
    assert [
        format_number(value, shown["numbers"]["orders"])
        for value in frame["orders"].dropna()
    ] == ["41.736"]


CAVEAT = (
    "Her durumdaki sipariş sayılır, iptal edilenler dahil. Kategori ya da satıcı "
    "eyaletine göre kırılımda birden fazla gruba giren sipariş her grupta bir kez "
    "sayılır."
)


def test_a_caveat_the_answer_already_says_is_not_shown_again():
    text = f"2018-01: 7.269 sipariş.\n\n*{CAVEAT}*"

    assert unsaid_caveats(text, [CAVEAT]) == []


def test_a_caveat_split_over_lines_in_the_answer_counts_as_said():
    text = "2018-01: 7.269 sipariş. " + CAVEAT.replace(" Kategori", "\nKategori")

    assert unsaid_caveats(text, [CAVEAT]) == []


def test_a_caveat_left_out_or_cut_short_is_still_shown():
    # As in a live answer: only the first sentence of the caveat was repeated.
    cut_short = "2018-01: 7.269 sipariş.\n\n*Not: Her durumdaki sipariş sayılır, iptal edilenler dahil.*"

    assert unsaid_caveats("2018-01: 7.269 sipariş.", [CAVEAT]) == [CAVEAT]
    assert unsaid_caveats(cut_short, [CAVEAT]) == [CAVEAT]


def test_ops_answer_does_not_repeat_the_caveat_it_already_says():
    result = {"columns": ["value"], "rows": [[7269]], "sql": "SELECT 1"}
    log = log_with(["run_metric"], [("run_metric", result)])
    reply = OpsReply(
        f"7.269 sipariş. {CAVEAT}", log, queries=["SELECT 1"], caveats=[CAVEAT]
    )

    view = view_of(Answer(Intent.OPS_METRIC, reply.display, reply, router_log()))

    assert view.caveats == []


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
        messages.UI_APPROVAL_AMOUNT: "115,00 BRL",
        messages.UI_APPROVAL_LEVEL: "kıdemli onay bekliyor",
    }


def test_the_card_only_writes_the_amount_differently():
    pending = dict(PENDING)

    approval_card(pending)

    assert pending == PENDING


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
        (
            MessageTooLong("1500 characters"),
            messages.UI_ERROR_TOO_LONG.format(limit=config.MAX_MESSAGE_CHARS),
        ),
        (QuestionLimitReached("60 questions"), messages.UI_ERROR_QUESTION_LIMIT),
        (KeyError("GEMINI_API_KEY"), messages.UI_ERROR_NOT_CONFIGURED),
        (wrapped(KeyError("GROQ_API_KEY")), messages.UI_ERROR_NOT_CONFIGURED),
        # What Gemini answers to a key it does not accept (2026-10-19).
        (
            RuntimeError(
                "400 INVALID_ARGUMENT. {'error': {'code': 400, 'message': 'API key "
                "not valid. Please pass a valid API key.', 'status': "
                "'INVALID_ARGUMENT', 'details': [{'reason': 'API_KEY_INVALID'}]}}"
            ),
            messages.UI_ERROR_KEY_REFUSED,
        ),
        # Groq's answer to a wrong key.
        (
            RuntimeError(
                "Error code: 401 - {'error': {'message': 'Invalid API Key', "
                "'type': 'invalid_request_error', 'code': 'invalid_api_key'}}"
            ),
            messages.UI_ERROR_KEY_REFUSED,
        ),
        (RuntimeError("403 PERMISSION_DENIED"), messages.UI_ERROR_KEY_REFUSED),
        # A KeyError about something else is not a missing key.
        (KeyError("order_ref"), messages.UI_ERROR_GENERIC),
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


@pytest.mark.parametrize(
    "text",
    [
        "Bakın: ![a[b]](https://example.com/?veri=SIP-1)",
        "Bakın: ![ref]\n\n[ref]: https://example.com/?veri=SIP-1",
        "Bakın: ![a](<https://example.com/?veri=(SIP-1)>)",
    ],
)
def test_no_form_of_markdown_image_is_left_to_draw(text, caplog):
    with caplog.at_level("WARNING"):
        cleaned = without_images(text)

    # Escaped, the two characters that start an image are plain text.
    assert "![" not in cleaned.replace("!\\[", "")
    assert "markdown images" in caplog.text


def test_links_and_plain_text_are_left_as_they_are():
    text = "Ayrıntı için [iade politikası](https://example.com/iade) bölüm 2. Not! [a]"

    assert without_images(text) == text


def test_tool_names_are_drawn_as_code_that_cannot_become_markdown():
    text = tools_text(["list_customer_orders", "![x](https://example.com/a.png)`"])

    assert text == "`list_customer_orders` → `![x](https://example.com/a.png)`"


def test_an_answer_without_tools_says_so():
    assert tools_text([]) == messages.UI_STEPS_NO_TOOLS
