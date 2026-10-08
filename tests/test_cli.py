"""Tests for the chat command, with scripted typing and a stand-in model."""

import pytest

from src import messages
from src.cli import chat, demo_customer
from tests.agent_harness import request_count, with_agent
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
def run_chat(synthetic_db_path, fake_policy_index, fake):
    """Run the chat with the given lines typed in; return prompts and output."""

    def run(typed):
        lines = iter(typed)
        prompts, shown = [], []

        def read(prompt):
            prompts.append(prompt)
            try:
                return next(lines)
            except StopIteration:
                raise EOFError from None

        with_agent(
            synthetic_db_path,
            fake_policy_index,
            fake,
            lambda agent: chat(agent, read, shown.append),
        )
        return prompts, shown

    return run


def test_question_and_answer(run_chat, fake):
    fake.script = ["Merhaba, nasıl yardımcı olabilirim?"]

    _, shown = run_chat(["Merhaba", "çık"])

    assert shown == [
        messages.CHAT_BANNER,
        "Merhaba, nasıl yardımcı olabilirim?",
        messages.CHAT_GOODBYE,
    ]


@pytest.mark.parametrize("word", ["çık", "ÇIK", "exit", "Quit", "  cik  "])
def test_exit_words_end_the_chat(run_chat, fake, word):
    _, shown = run_chat([word, "bu satır okunmaz"])

    assert shown == [messages.CHAT_BANNER, messages.CHAT_GOODBYE]
    assert fake.requests == []


def test_end_of_input_ends_the_chat(run_chat):
    _, shown = run_chat([])

    assert shown[-1] == messages.CHAT_GOODBYE


def test_empty_line_is_not_sent_to_the_model(run_chat, fake):
    run_chat(["", "   ", "çık"])

    assert fake.requests == []


def test_yes_writes_the_return_request(run_chat, fake, synthetic_db_path):
    fake.script = [[RETURN_CALL], "Onayınız istenecek."]

    prompts, shown = run_chat(["o_day14 hasarlı geldi, iade istiyorum", "e", "çık"])

    assert prompts[1] == messages.APPROVAL_QUESTION
    assert shown[1] == "Onayınız istenecek."
    assert shown[2].startswith("Oluşturulacak iade talebi:")
    assert "İade tutarı: 115.00 BRL" in shown[2]
    assert shown[3] == (
        "İade talebiniz oluşturuldu. Talep numarası: 3, durum: inceleme bekliyor."
    )
    assert request_count(synthetic_db_path) == 3


@pytest.mark.parametrize("typed", ["evet", "E", " Evet "])
def test_other_ways_of_saying_yes(run_chat, fake, synthetic_db_path, typed):
    fake.script = [[RETURN_CALL], "Onayınız istenecek."]

    run_chat(["o_day14 hasarlı geldi", typed, "çık"])

    assert request_count(synthetic_db_path) == 3


@pytest.mark.parametrize("typed", ["h", "hayır", "", "belki", "yes", "onaylıyorum"])
def test_anything_but_a_clear_yes_writes_nothing(
    run_chat, fake, synthetic_db_path, typed
):
    fake.script = [[RETURN_CALL], "Onayınız istenecek."]

    _, shown = run_chat(["o_day14 hasarlı geldi", typed, "çık"])

    assert shown[3] == messages.APPROVAL_DECLINED
    assert request_count(synthetic_db_path) == 2


def test_typing_yes_in_the_chat_itself_is_not_an_approval(
    run_chat, fake, synthetic_db_path
):
    # "e" typed as a chat message goes to the model; it approves nothing.
    fake.script = ["Neyi onaylamak istiyorsunuz?"]

    run_chat(["e", "çık"])

    assert request_count(synthetic_db_path) == 2
    assert len(fake.requests) == 1


def test_no_approval_question_without_a_pending_request(run_chat, fake):
    fake.script = ["Teslim edildi."]

    prompts, _ = run_chat(["o_day14 nerede?", "çık"])

    assert messages.APPROVAL_QUESTION not in prompts


def test_demo_customer_is_the_one_with_the_most_orders(synthetic_db):
    assert demo_customer(synthetic_db) == ALICE
