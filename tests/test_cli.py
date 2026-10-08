"""Tests for the chat command, with scripted typing and a stand-in model."""

import asyncio

import pytest

from src import messages
from src.agents.support import SupportAgent
from src.cli import chat, demo_customer
from src.guardrails.guarded_llm import GuardedLLM
from src.tools.escalation import EscalationQueue
from src.tools.session import open_session
from tests.fakes import FakeLLM
from tests.synthetic_data import ALICE

RETURN_CALL = (
    "create_return_request",
    {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"},
)


@pytest.fixture
def fake():
    return FakeLLM()


@pytest.fixture
def agent(synthetic_db, fake_policy_index, fake):
    session = open_session(synthetic_db, ALICE)
    llm = GuardedLLM(inner=fake, redactor=session.redactor())
    return SupportAgent(
        session, synthetic_db, fake_policy_index, EscalationQueue(), llm
    )


def run_chat(agent, typed):
    """Run the chat with the given lines typed in; return what was shown."""
    lines = iter(typed)
    prompts, shown = [], []

    def read(prompt):
        prompts.append(prompt)
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    asyncio.run(chat(agent, read, shown.append))
    return prompts, shown


def request_count(conn):
    return conn.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]


def test_question_and_answer(agent, fake):
    fake.script = ["Merhaba, nasıl yardımcı olabilirim?"]

    _, shown = run_chat(agent, ["Merhaba", "çık"])

    assert shown == [
        messages.CHAT_BANNER,
        "Merhaba, nasıl yardımcı olabilirim?",
        messages.CHAT_GOODBYE,
    ]


@pytest.mark.parametrize("word", ["çık", "ÇIK", "exit", "Quit", "  cik  "])
def test_exit_words_end_the_chat(agent, fake, word):
    _, shown = run_chat(agent, [word, "bu satır okunmaz"])

    assert shown == [messages.CHAT_BANNER, messages.CHAT_GOODBYE]
    assert fake.requests == []


def test_end_of_input_ends_the_chat(agent):
    _, shown = run_chat(agent, [])

    assert shown[-1] == messages.CHAT_GOODBYE


def test_empty_line_is_not_sent_to_the_model(agent, fake):
    run_chat(agent, ["", "   ", "çık"])

    assert fake.requests == []


def test_yes_writes_the_return_request(agent, fake, synthetic_db):
    fake.script = [[RETURN_CALL], "Onayınız istenecek."]

    prompts, shown = run_chat(
        agent, ["o_day14 hasarlı geldi, iade istiyorum", "e", "çık"]
    )

    assert prompts[1] == messages.APPROVAL_QUESTION
    assert shown[1] == "Onayınız istenecek."
    assert shown[2].startswith("Oluşturulacak iade talebi:")
    assert "İade tutarı: 115.00 BRL" in shown[2]
    assert shown[3] == (
        "İade talebiniz oluşturuldu. Talep numarası: 3, durum: inceleme bekliyor."
    )
    assert request_count(synthetic_db) == 3


@pytest.mark.parametrize("typed", ["evet", "E", " Evet "])
def test_other_ways_of_saying_yes(agent, fake, synthetic_db, typed):
    fake.script = [[RETURN_CALL], "Onayınız istenecek."]

    run_chat(agent, ["o_day14 hasarlı geldi", typed, "çık"])

    assert request_count(synthetic_db) == 3


@pytest.mark.parametrize("typed", ["h", "hayır", "", "belki", "yes", "onaylıyorum"])
def test_anything_but_a_clear_yes_writes_nothing(agent, fake, synthetic_db, typed):
    fake.script = [[RETURN_CALL], "Onayınız istenecek."]

    _, shown = run_chat(agent, ["o_day14 hasarlı geldi", typed, "çık"])

    assert shown[3] == messages.APPROVAL_DECLINED
    assert request_count(synthetic_db) == 2


def test_typing_yes_in_the_chat_itself_is_not_an_approval(agent, fake, synthetic_db):
    # "e" typed as a chat message goes to the model; it approves nothing.
    fake.script = ["Neyi onaylamak istiyorsunuz?"]

    run_chat(agent, ["e", "çık"])

    assert request_count(synthetic_db) == 2
    assert len(fake.requests) == 1


def test_no_approval_question_without_a_pending_request(agent, fake):
    fake.script = ["Teslim edildi."]

    prompts, _ = run_chat(agent, ["o_day14 nerede?", "çık"])

    assert messages.APPROVAL_QUESTION not in prompts


def test_demo_customer_is_the_one_with_the_most_orders(synthetic_db):
    assert demo_customer(synthetic_db) == ALICE
