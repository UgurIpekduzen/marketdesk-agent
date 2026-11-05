"""Tests for a failure in the middle of the approval flow, with a stand-in model.

A provider that fails (busy, quota) must not leave the conversation in a
state that writes something or shows a card nobody asked about: what was
shown can still be answered, what was not shown is dropped, and a click
already made is never repeated.
"""

import functools

import pytest

from tests.agent_harness import request_count, with_agent
from tests.fakes import FakeLLM

RETURN_CALL = (
    "create_return_request",
    {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"},
)
# The synthetic database starts with two return requests.
ROWS_BEFORE = 2


class ProviderBusyError(Exception):
    status_code = 503


@pytest.fixture
def fake():
    return FakeLLM()


def run_scenario_of_run(synthetic_db_path, fake_policy_index, fake, scenario):
    return with_agent(synthetic_db_path, fake_policy_index, fake, scenario)


@pytest.fixture
def run(synthetic_db_path, fake_policy_index, fake):

    return functools.partial(
        run_scenario_of_run, synthetic_db_path, fake_policy_index, fake
    )


def instructions(request: dict) -> str:
    return request["messages"][0]["blocks"][0]["text"]


async def scenario_of_shown_card_survives_a_failure(agent):
    shown = (await agent.ask("o_day14 hasarlı geldi, iade.")).awaiting_approval
    with pytest.raises(ProviderBusyError):
        await agent.ask("Ne kadar sürer?")
    still_waiting = (await agent.ask("Tamam.")).awaiting_approval
    return shown, still_waiting, await agent.approve()


def test_shown_card_survives_a_failure(run, fake, synthetic_db_path):
    fake.script = [[RETURN_CALL], "Onayınız istenecek.", ProviderBusyError(), "Peki."]

    shown, still_waiting, _ = run(scenario_of_shown_card_survives_a_failure)

    assert still_waiting == shown
    assert request_count(synthetic_db_path) == ROWS_BEFORE + 1


async def scenario_of_unseen_request_dropped_on_failure(agent):
    with pytest.raises(ProviderBusyError):
        await agent.ask("o_day14 hasarlı geldi, iade.")
    waiting = await agent._orders.pending_approval()
    reply = await agent.ask("Ne oldu?")
    return waiting, reply.awaiting_approval, await agent.approve()


def test_unseen_request_dropped_on_failure(run, fake, synthetic_db_path):
    # The model asks for the request, then the provider fails before the
    # answer that would have come with the card.
    fake.script = [
        [RETURN_CALL],
        ProviderBusyError(),
        "Bir sorun oldu, tekrar deneyelim.",
    ]

    waiting, card_with_next_answer, _ = run(
        scenario_of_unseen_request_dropped_on_failure
    )

    assert waiting is None
    assert card_with_next_answer is None
    # A click that comes anyway finds nothing to write.
    assert request_count(synthetic_db_path) == ROWS_BEFORE
    # The model is told, in its instructions, that nothing was created.
    assert instructions(fake.requests[-1]).endswith(
        "- SIP-1: a message failed while this return request was waiting for "
        "approval; it was dropped and nothing was created.\n"
    )


async def scenario_of_failure_after_click_writes_no_more(agent):
    await agent.ask("o_day14 hasarlı geldi, iade.")
    await agent.approve()
    with pytest.raises(ProviderBusyError):
        await agent.ask("Teşekkürler.")
    return await agent.ask("Talebim açıldı mı? Açılmadıysa aç.")


def test_failure_after_click_writes_no_more(run, fake, synthetic_db_path):
    fake.script = [
        [RETURN_CALL],
        "Onayınız istenecek.",
        ProviderBusyError(),
        # The model tries to open the request again.
        [RETURN_CALL],
        "Talebiniz zaten açık.",
    ]

    reply = run(scenario_of_failure_after_click_writes_no_more)

    assert reply.awaiting_approval is None
    assert request_count(synthetic_db_path) == ROWS_BEFORE + 1
    # The record of the click is in the instructions of every later call,
    # the failed message or not.
    assert "the customer approved on screen" in instructions(fake.requests[-1])
