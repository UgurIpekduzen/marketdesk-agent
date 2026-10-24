"""Tests for the chat session behind the user interface: a real order
server process, a stand-in model, no page framework."""

import asyncio
import gc
import logging
import os
import threading
from pathlib import Path

import pytest

import config
from src import messages
from src.orchestrator import Intent, SessionType
from src.ui.call_budget import CallBudget, CallBudgetReached
from src.ui.chat_session import (
    ApprovalWaiting,
    ChatSession,
    MessageTooLong,
    SessionClosed,
)
from src.ui.question_limit import QuestionLimit, QuestionLimitReached
from src.ui.view import friendly_error
from tests.agent_harness import request_count
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE

RETURN = {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"}


@pytest.fixture
def open_session(synthetic_db_path, fake_policy_index):
    """Open sessions with a scripted model; all are closed after the test."""
    sessions = []

    def start(script, customer=ALICE, question_limit=None, call_budget=None):
        session = ChatSession(
            synthetic_db_path,
            fake_policy_index,
            customer,
            FakeLLM(script=list(script)),
            question_limit=question_limit,
            call_budget=call_budget,
        )
        sessions.append(session)
        return session

    yield start
    for session in sessions:
        session.close()


def test_customer_session_answers_through_the_router(open_session):
    session = open_session(
        ["support", [("get_order_status", {"order_ref": "o_day14"})], "Teslim edildi."]
    )

    answer = session.ask("o_day14 nerede?")

    assert session.session_type is SessionType.CUSTOMER
    assert answer.intent is Intent.SUPPORT
    assert answer.display == "Teslim edildi."
    assert answer.reply.log.tool_calls == ["get_order_status"]


def test_conversation_and_aliases_are_kept_between_questions(open_session):
    session = open_session(
        [
            "support",
            [("list_customer_orders", {})],
            "Siparişleriniz listelendi.",
            "support",
            # SIP-1 only means something if the first answer's session lives on.
            [("get_order_status", {"order_ref": "SIP-1"})],
            "SIP-1 teslim edildi.",
        ]
    )

    session.ask("Siparişlerim neler?")
    answer = session.ask("İlki ne durumda?")

    (_, result), *_ = answer.reply.log.tool_results
    assert result["order"] == "SIP-1"
    assert "error" not in result


def test_request_is_written_only_after_approve(open_session, synthetic_db_path):
    session = open_session(
        ["support", [("create_return_request", RETURN)], "Onayınız istenecek."]
    )

    at_start = request_count(synthetic_db_path)

    answer = session.ask("o_day14 hasarlı geldi, iade istiyorum")
    after_asking = request_count(synthetic_db_path)
    message = session.approve()

    assert answer.awaiting_approval["refund_amount"] == "115.00"
    assert after_asking == at_start
    assert request_count(synthetic_db_path) == at_start + 1
    assert "oluşturuldu" in message


def test_a_message_is_refused_on_the_server_while_a_card_waits(
    open_session, synthetic_db_path
):
    session = open_session(
        ["support", [("create_return_request", RETURN)], "Onayınız istenecek."]
    )
    session.ask("o_day14 hasarlı geldi, iade istiyorum")
    model_calls_before = len(session._provider_llm.requests)

    with pytest.raises(ApprovalWaiting):
        session.ask("Bir de başka bir siparişim var, onu da iade edin.")

    # The model was not asked, and the card still waits for its answer.
    assert len(session._provider_llm.requests) == model_calls_before
    assert "oluşturuldu" in session.approve()
    assert request_count(synthetic_db_path) == 3


def test_after_the_answer_to_the_card_messages_are_taken_again(open_session):
    session = open_session(
        [
            "support",
            [("create_return_request", RETURN)],
            "Onayınız istenecek.",
            "support",
            "Buyurun.",
        ]
    )
    session.ask("o_day14 hasarlı geldi, iade istiyorum")
    session.decline()

    assert session.ask("Başka bir sorum var.").display == "Buyurun."


def test_the_refusal_while_a_card_waits_has_its_own_text():
    from src.i18n import Language

    for language in Language:
        text = friendly_error(ApprovalWaiting("x"), language)
        assert text
        assert text != friendly_error(MessageTooLong("x"), language)


def test_a_click_on_an_old_card_writes_nothing(open_session, synthetic_db_path):
    session = open_session(
        ["support", [("create_return_request", RETURN)], "Onayınız istenecek."]
    )
    answer = session.ask("o_day14 hasarlı geldi, iade istiyorum")
    old = dict(answer.awaiting_approval, refund_amount="999.00")
    at_start = request_count(synthetic_db_path)

    message = session.approve(old)

    assert request_count(synthetic_db_path) == at_start
    assert messages.STALE_CARD in message


def test_decline_writes_nothing(open_session, synthetic_db_path):
    session = open_session(
        ["support", [("create_return_request", RETURN)], "Onayınız istenecek."]
    )

    at_start = request_count(synthetic_db_path)

    session.ask("o_day14 hasarlı geldi, iade istiyorum")
    session.decline()

    assert request_count(synthetic_db_path) == at_start


def test_ops_session_has_no_customer_and_answers_from_the_views(open_session):
    session = open_session(
        [
            "ops_metric",
            [("run_sql", {"query": "SELECT COUNT(*) AS n FROM v_orders"})],
            "29 sipariş.",
        ],
        customer=None,
    )

    answer = session.ask("Kaç sipariş var?")

    assert session.session_type is SessionType.OPS
    assert answer.reply.queries
    assert answer.awaiting_approval is None


def test_customer_session_refuses_an_ops_question(open_session):
    session = open_session(["ops_metric"])

    answer = session.ask("Geçen ayın cirosu ne kadar?")

    assert answer.refused


def test_error_in_one_question_leaves_the_session_usable(open_session):
    session = open_session(["support", "Merhaba."])
    session._do(lambda router: _fail())

    with pytest.raises(ZeroDivisionError):
        session._do(lambda router: _divide())

    assert session.ask("Merhaba").display == "Merhaba."


def child_processes() -> set[int]:
    """Process ids of this process's children that are still running."""
    children = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        # After the name: state, then the parent's process id.
        if int(fields[1]) == os.getpid() and fields[0] != "Z":
            children.add(int(entry.name))
    return children


async def _fail():
    return None


async def _divide():
    return 1 / 0


def test_each_question_marks_the_session_as_used(open_session):
    session = open_session(["support", "Merhaba."])
    session.last_used = 0.0

    session.ask("Merhaba")

    assert session.last_used > 0.0


def test_a_message_over_the_limit_never_reaches_the_model(open_session):
    # An empty script: a model call would fail the test.
    session = open_session([])

    with pytest.raises(MessageTooLong):
        session.ask("a" * (config.MAX_MESSAGE_CHARS + 1))


def test_a_message_at_the_limit_is_answered(open_session):
    session = open_session(["support", "Merhaba."])

    answer = session.ask("a" * config.MAX_MESSAGE_CHARS)

    assert answer.display == "Merhaba."


def test_sessions_share_the_question_limit_and_approvals_do_not_count(
    open_session,
):
    limit = QuestionLimit(per_hour=1)
    first = open_session(["support", "Birinci."], question_limit=limit)
    second = open_session([], question_limit=limit)

    first.ask("Merhaba")
    first.decline()

    with pytest.raises(QuestionLimitReached):
        second.ask("Merhaba")


def model_requests(session):
    """The requests the session's stand-in model has received."""
    return session._provider_llm.inner.requests


def test_the_call_budget_counts_every_model_call(open_session):
    # The router's call, one step with a tool, and the answer: three calls.
    budget = CallBudget(per_day=3)
    session = open_session(
        ["support", [("get_order_status", {"order_ref": "o_day14"})], "Teslim."],
        call_budget=budget,
    )

    session.ask("o_day14 nerede?")

    with pytest.raises(CallBudgetReached):
        session.ask("Bir soru daha")
    assert len(model_requests(session)) == 3


def test_a_run_that_reaches_the_budget_stops_in_the_middle(open_session):
    budget = CallBudget(per_day=2)
    session = open_session(
        ["support", [("get_order_status", {"order_ref": "o_day14"})], "Teslim."],
        call_budget=budget,
    )

    with pytest.raises(Exception) as failure:
        session.ask("o_day14 nerede?")

    assert friendly_error(failure.value) == messages.UI_ERROR_DAILY_BUDGET
    assert len(model_requests(session)) == 2


def test_sessions_share_the_call_budget(open_session):
    budget = CallBudget(per_day=1)
    first = open_session(["out_of_scope"], call_budget=budget)
    second = open_session([], call_budget=budget)

    first.ask("Bir şiir yaz")

    with pytest.raises(CallBudgetReached):
        second.ask("Merhaba")
    assert model_requests(second) == []


def test_clicks_on_the_card_use_no_model_call_and_write_once(
    open_session, synthetic_db_path
):
    budget = CallBudget(per_day=3)
    session = open_session(
        ["support", [("create_return_request", RETURN)], "Onayınız istenecek."],
        call_budget=budget,
    )
    at_start = request_count(synthetic_db_path)
    session.ask("o_day14 hasarlı geldi, iade istiyorum")

    # The budget is used up by the question; the clicks still work.
    replies = [session.approve() for _ in range(3)] + [session.decline()]

    assert "oluşturuldu" in replies[0]
    assert request_count(synthetic_db_path) == at_start + 1
    assert len(model_requests(session)) == 3


def test_closing_ends_the_thread_and_refuses_more_work(open_session):
    session = open_session([])
    thread = session._thread

    session.close()
    session.close()

    assert session.closed
    assert not thread.is_alive()
    with pytest.raises(SessionClosed):
        session.ask("Merhaba")


def test_closing_stops_the_order_server_process(open_session):
    before = child_processes()
    session = open_session([])
    while_open = child_processes()

    session.close()

    assert len(while_open - before) == 1
    assert child_processes() == before


def test_session_that_cannot_start_raises_and_leaves_no_thread(fake_policy_index):
    threads_before = threading.active_count()

    with pytest.raises(Exception):  # noqa: B017
        ChatSession("no/such/database.db", fake_policy_index, ALICE, FakeLLM())

    assert threading.active_count() == threads_before


def test_two_sessions_do_not_share_a_conversation(open_session):
    first = open_session(["support", "Birinci."])
    second = open_session(["support", "İkinci."])

    assert first.ask("Merhaba").display == "Birinci."
    assert second.ask("Merhaba").display == "İkinci."


# Set by the closing task of CleansUpLater once it has run to its end.
CLEANED: list = []


class CleansUpLater(FakeLLM):
    """A model whose client leaves its own closing behind as a task, as the
    Gemini client does when it is garbage collected while a loop runs."""

    async def achat(self, messages, **kwargs):
        async def close_client():
            await asyncio.sleep(0.5)
            CLEANED.append(True)

        asyncio.get_running_loop().create_task(close_client())
        return await super().achat(messages, **kwargs)


def test_tasks_left_on_the_loop_finish_when_the_session_closes(
    synthetic_db_path, caplog
):
    CLEANED.clear()
    session = ChatSession(
        synthetic_db_path,
        provider_llm=CleansUpLater(script=["ops_metric", "Hazır."]),
    )
    session.ask("Kaç sipariş var?")

    with caplog.at_level(logging.ERROR, logger="asyncio"):
        session.close()
        gc.collect()

    assert CLEANED
    assert "Task was destroyed" not in caplog.text
