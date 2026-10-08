"""Tests for handing a case over to a person."""

import logging

import pytest

from src import messages
from src.guardrails.pii import hash_id
from src.tools.escalation import (
    MAX_SUMMARY_LENGTH,
    PRIORITIES,
    EscalationQueue,
    escalate_to_human,
)
from src.tools.session import Session
from tests.synthetic_data import ALICE

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"


@pytest.fixture
def alice():
    return Session(ALICE)


@pytest.fixture
def queue():
    return EscalationQueue()


def test_escalation_returns_a_ticket_number(alice, queue):
    answer = escalate_to_human(alice, queue, "SIP-1 has no delivery date.", "high")

    assert answer == {
        "ticket": "ESC-1",
        "priority": "high",
        "message": messages.ESCALATED,
    }


def test_tickets_are_numbered_in_order_and_kept_in_the_queue(alice, queue):
    first = escalate_to_human(alice, queue, "First case.")
    second = escalate_to_human(alice, queue, "Second case.", "low")

    assert (first["ticket"], second["ticket"]) == ("ESC-1", "ESC-2")
    assert [ticket.summary for ticket in queue.tickets] == [
        "First case.",
        "Second case.",
    ]
    assert [ticket.priority for ticket in queue.tickets] == ["normal", "low"]


def test_escalation_changes_no_record(synthetic_db, alice, queue):
    before = synthetic_db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]

    escalate_to_human(alice, queue, "The customer asks for a person.")

    after = synthetic_db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]
    assert after == before
    assert synthetic_db.total_changes == 0


def test_escalation_is_logged_without_the_customer_id(alice, queue, caplog):
    with caplog.at_level(logging.INFO, logger="src.tools.escalation"):
        escalate_to_human(alice, queue, "SIP-1 has no delivery date.", "high")

    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert "ticket=ESC-1" in line
    assert "priority=high" in line
    assert f"customer={hash_id(ALICE)}" in line
    assert ALICE not in line


def test_raw_ids_in_the_summary_are_masked_everywhere(alice, queue, caplog):
    with caplog.at_level(logging.INFO, logger="src.tools.escalation"):
        escalate_to_human(alice, queue, f"Order {RAW_ID} arrived broken.")

    assert queue.tickets[0].summary == "Order [id] arrived broken."
    assert RAW_ID not in caplog.text


def test_ticket_holds_the_customer_as_a_hash_only(alice, queue):
    escalate_to_human(alice, queue, "The customer asks for a person.")

    assert queue.tickets[0].customer_hash == hash_id(ALICE)
    assert ALICE not in repr(queue.tickets[0])


def test_long_summary_is_cut(alice, queue):
    escalate_to_human(alice, queue, "x" * (MAX_SUMMARY_LENGTH + 100))

    assert len(queue.tickets[0].summary) == MAX_SUMMARY_LENGTH


@pytest.mark.parametrize("summary", ["", "   ", "\n"])
def test_empty_summary_is_refused(alice, queue, summary):
    answer = escalate_to_human(alice, queue, summary)

    assert answer == {"error": "EMPTY_SUMMARY", "message": messages.EMPTY_SUMMARY}
    assert queue.tickets == []


def test_unknown_priority_is_refused_with_the_allowed_values(alice, queue):
    answer = escalate_to_human(alice, queue, "A case.", "urgent")

    assert answer["error"] == "INVALID_PRIORITY"
    for priority in PRIORITIES:
        assert priority in answer["message"]
    assert queue.tickets == []


def test_every_queue_starts_empty():
    assert EscalationQueue().tickets == []
