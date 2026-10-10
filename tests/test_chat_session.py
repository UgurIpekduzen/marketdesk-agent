"""Tests for the chat session behind the user interface: a real order
server process, a stand-in model, no page framework."""

import os
import threading
from pathlib import Path

import pytest

from src.orchestrator import Intent, SessionType
from src.ui.chat_session import ChatSession, SessionClosed
from tests.agent_harness import request_count
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE

RETURN = {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"}


@pytest.fixture
def open_session(synthetic_db_path, fake_policy_index):
    """Open sessions with a scripted model; all are closed after the test."""
    sessions = []

    def start(script, customer=ALICE):
        session = ChatSession(
            synthetic_db_path, fake_policy_index, customer, FakeLLM(script=list(script))
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
