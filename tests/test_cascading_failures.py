"""Tests for a failure in the middle of the approval flow, with a stand-in model.

A provider that fails (busy, quota) must not leave the conversation in a
state that writes something or shows a card nobody asked about: what was
shown can still be answered, what was not shown is dropped, and a click
already made is never repeated.
"""

import pytest

from tests.agent_harness import request_count, with_agent
from tests.fakes import FakeLLM

RETURN_CALL = (
    "create_return_request",
    {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"},
)
# The synthetic database starts with two return requests.
ROWS_BEFORE = 2


class ProviderBusy(Exception):
    status_code = 503


@pytest.fixture
def fake():
    return FakeLLM()


@pytest.fixture
def run(synthetic_db_path, fake_policy_index, fake):
    def run_scenario(scenario):
        return with_agent(synthetic_db_path, fake_policy_index, fake, scenario)

    return run_scenario


def user_texts(request: dict) -> list[str]:
    return [
        block["text"]
        for message in request["messages"]
        if message["role"] == "user"
        for block in message["blocks"]
    ]


def test_a_card_shown_before_a_failure_can_still_be_answered(
    run, fake, synthetic_db_path
):
    fake.script = [[RETURN_CALL], "Onayınız istenecek.", ProviderBusy(), "Peki."]

    async def scenario(agent):
        shown = (await agent.ask("o_day14 hasarlı geldi, iade.")).awaiting_approval
        with pytest.raises(ProviderBusy):
            await agent.ask("Ne kadar sürer?")
        still_waiting = (await agent.ask("Tamam.")).awaiting_approval
        return shown, still_waiting, await agent.approve()

    shown, still_waiting, _ = run(scenario)

    assert still_waiting == shown
    assert request_count(synthetic_db_path) == ROWS_BEFORE + 1


def test_a_request_the_person_never_saw_is_dropped_when_the_message_fails(
    run, fake, synthetic_db_path
):
    # The model asks for the request, then the provider fails before the
    # answer that would have come with the card.
    fake.script = [[RETURN_CALL], ProviderBusy(), "Bir sorun oldu, tekrar deneyelim."]

    async def scenario(agent):
        with pytest.raises(ProviderBusy):
            await agent.ask("o_day14 hasarlı geldi, iade.")
        waiting = await agent._orders.pending_approval()
        reply = await agent.ask("Ne oldu?")
        return waiting, reply.awaiting_approval, await agent.approve()

    waiting, card_with_next_answer, _ = run(scenario)

    assert waiting is None
    assert card_with_next_answer is None
    # A click that comes anyway finds nothing to write.
    assert request_count(synthetic_db_path) == ROWS_BEFORE
    # The model is told, with the next message, that nothing was created.
    assert user_texts(fake.requests[-1])[-1].startswith(
        "[Note from the system: the last message failed while a return request"
    )


def test_a_failure_after_the_click_writes_nothing_more(run, fake, synthetic_db_path):
    fake.script = [
        [RETURN_CALL],
        "Onayınız istenecek.",
        ProviderBusy(),
        # The model tries to open the request again.
        [RETURN_CALL],
        "Talebiniz zaten açık.",
    ]

    async def scenario(agent):
        await agent.ask("o_day14 hasarlı geldi, iade.")
        await agent.approve()
        with pytest.raises(ProviderBusy):
            await agent.ask("Teşekkürler.")
        return await agent.ask("Talebim açıldı mı? Açılmadıysa aç.")

    reply = run(scenario)

    assert reply.awaiting_approval is None
    assert request_count(synthetic_db_path) == ROWS_BEFORE + 1
    # The note on the click was sent with the message that failed; that
    # message stays in the conversation, so the model still gets the note.
    assert any(
        text.startswith("[Note from the system: the customer approved on screen")
        for text in user_texts(fake.requests[-1])
    )
