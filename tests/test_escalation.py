"""Tests for handing a case over to a person."""

import logging
import sqlite3
from datetime import date

import pytest

from src import messages
from src.guardrails.pii import hash_id
from src.tools.escalation import (
    MAX_SUMMARY_LENGTH,
    PRIORITIES,
    TICKET_OPEN,
    TICKETS_TABLE,
    ensure_tickets_table,
    escalate_to_human,
)
from src.tools.session import Session
from tests.synthetic_data import ALICE

RAW_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"


@pytest.fixture
def alice():
    return Session(ALICE)


@pytest.fixture
def conn(synthetic_db_path):
    connection = sqlite3.connect(synthetic_db_path)
    yield connection
    connection.close()


def tickets(conn) -> list[tuple]:
    return conn.execute(
        "SELECT id, customer_hash, priority, summary, status, created_at "
        f"FROM {TICKETS_TABLE} ORDER BY id"
    ).fetchall()


def test_escalation_returns_a_ticket_number(alice, conn):
    answer = escalate_to_human(alice, conn, "SIP-1 has no delivery date.", "high")

    assert answer == {
        "ticket": "ESC-1",
        "priority": "high",
        "message": messages.ESCALATED,
    }


def test_tickets_are_numbered_in_order(alice, conn):
    first = escalate_to_human(alice, conn, "First case.")
    second = escalate_to_human(alice, conn, "Second case.", "low")

    assert (first["ticket"], second["ticket"]) == ("ESC-1", "ESC-2")
    assert tickets(conn) == [
        (
            1,
            hash_id(ALICE),
            "normal",
            "First case.",
            TICKET_OPEN,
            "2018-09-01 00:00:00",
        ),
        (2, hash_id(ALICE), "low", "Second case.", TICKET_OPEN, "2018-09-01 00:00:00"),
    ]


def test_ticket_has_the_simulated_date(alice, conn):
    escalate_to_human(alice, conn, "A case.", today=date(2018, 8, 30))

    assert tickets(conn)[0][5] == "2018-08-30 00:00:00"


def test_tickets_outlive_the_connection(alice, synthetic_db_path):
    first = sqlite3.connect(synthetic_db_path)
    escalate_to_human(alice, first, "A case.")
    first.close()

    second = sqlite3.connect(synthetic_db_path)
    try:
        assert len(tickets(second)) == 1
    finally:
        second.close()


def test_escalation_writes_only_the_ticket(synthetic_db, alice):
    before = synthetic_db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]

    escalate_to_human(alice, synthetic_db, "The customer asks for a person.")

    after = synthetic_db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]
    assert after == before
    # One row changed in all: the ticket.
    assert synthetic_db.total_changes == 1


def test_escalation_log_has_no_customer_id(alice, conn, caplog):
    with caplog.at_level(logging.INFO, logger="src.tools.escalation"):
        escalate_to_human(alice, conn, "SIP-1 has no delivery date.", "high")

    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert "ticket=ESC-1" in line
    assert "priority=high" in line
    assert f"customer={hash_id(ALICE)}" in line
    assert ALICE not in line


def test_summary_ids_are_masked(alice, conn, caplog):
    with caplog.at_level(logging.INFO, logger="src.tools.escalation"):
        escalate_to_human(alice, conn, f"Order {RAW_ID} arrived broken.")

    assert tickets(conn)[0][3] == "Order [id] arrived broken."
    assert RAW_ID not in caplog.text


def test_ticket_holds_customer_hash_only(alice, conn):
    escalate_to_human(alice, conn, "The customer asks for a person.")

    assert tickets(conn)[0][1] == hash_id(ALICE)
    assert ALICE not in repr(tickets(conn))


def test_long_summary_is_cut(alice, conn):
    escalate_to_human(alice, conn, "x" * (MAX_SUMMARY_LENGTH + 100))

    assert len(tickets(conn)[0][3]) == MAX_SUMMARY_LENGTH


@pytest.mark.parametrize("summary", ["", "   ", "\n"])
def test_empty_summary_is_refused(alice, conn, summary):
    answer = escalate_to_human(alice, conn, summary)

    assert answer == {"error": "EMPTY_SUMMARY", "message": messages.EMPTY_SUMMARY}
    assert tickets(conn) == []


def test_unknown_priority_lists_allowed(alice, conn):
    answer = escalate_to_human(alice, conn, "A case.", "urgent")

    assert answer["error"] == "INVALID_PRIORITY"
    for priority in PRIORITIES:
        assert priority in answer["message"]
    assert tickets(conn) == []


def test_missing_table_is_created(alice, conn):
    conn.execute(f"DROP TABLE {TICKETS_TABLE}")

    ensure_tickets_table(conn)
    escalate_to_human(alice, conn, "A case.")
    ensure_tickets_table(conn)

    assert len(tickets(conn)) == 1
