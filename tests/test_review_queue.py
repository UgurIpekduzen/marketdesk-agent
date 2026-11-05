"""Tests for the support rep's review queue: decisions made in code only."""

import functools
import hashlib
import logging
import sqlite3
import threading

import pytest

from src import messages
from src.guardrails.pii import hash_id
from src.rules.returns import RequestStatus
from src.tools.escalation import TICKETS_TABLE, escalate_to_human
from src.tools.review_queue import (
    DECIDED_SHOWN,
    REP_IDENTITY,
    NotARepSessionError,
    ReviewQueue,
)
from src.tools.session import Session
from tests.synthetic_data import ALICE

REVIEW = RequestStatus.PENDING_REVIEW
SENIOR = RequestStatus.PENDING_SENIOR


def add_request(db_path, order_id="o_day14", status=REVIEW, amount=115.0) -> int:
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO return_requests (order_id, customer_unique_id, reason, "
                "refund_amount, status, created_at) VALUES (?, ?, 'damaged', ?, ?, "
                "'2018-09-01 00:00:00')",
                (order_id, ALICE, amount, status),
            )
        return cursor.lastrowid
    finally:
        conn.close()


def status_of(db_path, request_id) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT status FROM return_requests WHERE id = ?", (request_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def add_ticket(db_path, summary="Müşteri bir temsilci istiyor.", priority="normal"):
    conn = sqlite3.connect(db_path)
    try:
        return escalate_to_human(Session(ALICE), conn, summary, priority)["ticket"]
    finally:
        conn.close()


@pytest.fixture
def queue(synthetic_db_path):
    """A queue on a copy whose own requests (set up for the rule tests) are gone."""
    conn = sqlite3.connect(synthetic_db_path)
    with conn:
        conn.execute("DELETE FROM return_requests")
    conn.close()
    return ReviewQueue(synthetic_db_path, REP_IDENTITY)


# --- Who may hold a queue -----------------------------------------------------


@pytest.mark.parametrize(
    "identity", [("customer", "recent_delivery"), ("ops",), (), ("rep", "x"), ("REP",)]
)
def test_only_the_rep_session_gets_a_queue(synthetic_db_path, identity):
    with pytest.raises(NotARepSessionError):
        ReviewQueue(synthetic_db_path, identity)


def test_missing_tickets_table_is_created(synthetic_db_path):
    conn = sqlite3.connect(synthetic_db_path)
    conn.execute(f"DROP TABLE {TICKETS_TABLE}")
    conn.close()

    assert ReviewQueue(synthetic_db_path, REP_IDENTITY).open_tickets() == []


# --- What the rep sees --------------------------------------------------------


def test_waiting_requests_show_hashes(queue, synthetic_db_path):
    review = add_request(synthetic_db_path)
    senior = add_request(synthetic_db_path, "o_day15", SENIOR, 620.0)

    rows = queue.waiting_requests()

    assert [(row.request_id, row.status) for row in rows] == [
        (review, REVIEW),
        (senior, SENIOR),
    ]
    assert rows[0].order_key == hash_id("o_day14")
    assert rows[0].customer_key == hash_id(ALICE)
    assert rows[0].reason == "damaged"
    assert rows[0].amount == "115.0"
    assert ALICE not in repr(rows)
    assert "o_day14" not in repr(rows)


def test_tickets_show_high_priority_first(queue, synthetic_db_path):
    add_ticket(synthetic_db_path, "Önce gelen.", "normal")
    add_ticket(synthetic_db_path, "Acil olan.", "high")

    tickets = queue.open_tickets()

    assert [t.summary for t in tickets] == ["Acil olan.", "Önce gelen."]
    assert [t.number for t in tickets] == ["ESC-2", "ESC-1"]
    assert tickets[0].customer_key == hash_id(ALICE)


# --- Deciding -------------------------------------------------------------------


@pytest.mark.parametrize("decision", [RequestStatus.APPROVED, RequestStatus.REJECTED])
def test_waiting_request_is_decided_once(queue, synthetic_db_path, decision):
    request_id = add_request(synthetic_db_path)

    assert queue.decide(request_id, decision) == {
        "request": request_id,
        "status": decision,
    }
    assert status_of(synthetic_db_path, request_id) == decision
    assert queue.waiting_requests() == []
    assert [row.request_id for row in queue.decided_requests()] == [request_id]

    # A second click finds it decided and changes nothing.
    other = (
        RequestStatus.REJECTED
        if decision == RequestStatus.APPROVED
        else RequestStatus.APPROVED
    )
    assert queue.decide(request_id, other)["error"] == "ALREADY_DECIDED"
    assert status_of(synthetic_db_path, request_id) == decision


@pytest.mark.parametrize("decision", [RequestStatus.APPROVED, RequestStatus.REJECTED])
def test_senior_request_is_not_decided_here(queue, synthetic_db_path, decision):
    request_id = add_request(synthetic_db_path, status=SENIOR, amount=620.0)

    answer = queue.decide(request_id, decision)

    assert answer == {"error": "SENIOR_ONLY", "message": messages.REVIEW_SENIOR_ONLY}
    assert status_of(synthetic_db_path, request_id) == SENIOR


def test_an_unknown_request_is_not_found(queue):
    assert queue.decide(999, RequestStatus.APPROVED)["error"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "decision", ["PENDING_REVIEW", "PENDING_SENIOR", "DELETED", ""]
)
def test_only_approve_and_reject_decide(queue, synthetic_db_path, decision):
    request_id = add_request(synthetic_db_path)

    assert queue.decide(request_id, decision)["error"] == "INVALID_DECISION"
    assert status_of(synthetic_db_path, request_id) == REVIEW


def test_decision_changes_one_row_no_order(queue, synthetic_db_path):
    first = add_request(synthetic_db_path)
    second = add_request(synthetic_db_path, "o_day15")
    conn = sqlite3.connect(synthetic_db_path)
    orders_before = conn.execute("SELECT * FROM orders ORDER BY rowid").fetchall()

    queue.decide(first, RequestStatus.APPROVED)

    assert (
        conn.execute("SELECT * FROM orders ORDER BY rowid").fetchall() == orders_before
    )
    conn.close()
    assert status_of(synthetic_db_path, second) == REVIEW


def test_decided_requests_show_the_latest(queue, synthetic_db_path):
    ids = [add_request(synthetic_db_path, f"o_{n}") for n in range(DECIDED_SHOWN + 3)]
    for request_id in ids:
        queue.decide(request_id, RequestStatus.REJECTED)

    shown = [row.request_id for row in queue.decided_requests()]

    assert shown == list(reversed(ids))[:DECIDED_SHOWN]


def test_decision_log_has_no_raw_ids(queue, synthetic_db_path, caplog):
    request_id = add_request(synthetic_db_path)

    with caplog.at_level(logging.INFO, logger="src.tools.review_queue"):
        queue.decide(request_id, RequestStatus.APPROVED)

    line = caplog.records[0].getMessage()
    assert f"order={hash_id('o_day14')}" in line
    assert "status=APPROVED" in line
    assert "o_day14" not in caplog.text
    assert ALICE not in caplog.text


# --- Tickets --------------------------------------------------------------------


def test_a_ticket_is_closed_once(queue, synthetic_db_path):
    add_ticket(synthetic_db_path)
    (ticket,) = queue.open_tickets()

    assert queue.close_ticket(ticket.ticket_id) == {
        "ticket": "ESC-1",
        "status": "CLOSED",
    }
    assert queue.open_tickets() == []
    assert queue.close_ticket(ticket.ticket_id)["error"] == "ALREADY_CLOSED"


def test_an_unknown_ticket_is_not_found(queue):
    assert queue.close_ticket(999)["error"] == "NOT_FOUND"


# --- Least privilege of the console's connection -----------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE return_requests SET refund_amount = 1000",
        f"UPDATE {TICKETS_TABLE} SET summary = 'x'",
        "INSERT INTO return_requests (order_id) VALUES ('x')",
        "DELETE FROM return_requests",
        "UPDATE orders SET order_status = 'canceled'",
        "DROP TABLE orders",
    ],
)
def test_console_may_change_only_status(queue, synthetic_db_path, sql):
    add_request(synthetic_db_path)
    add_ticket(synthetic_db_path)
    before = hashlib.sha256(synthetic_db_path.read_bytes()).hexdigest()
    conn = queue._connect()

    with pytest.raises(sqlite3.DatabaseError, match="not authorized"), conn:
        conn.execute(sql)
    conn.close()

    assert hashlib.sha256(synthetic_db_path.read_bytes()).hexdigest() == before


# --- Several reps at once --------------------------------------------------------


def decide_of_decide_all_at_once(start, answers, queue, request_id, index, decision):
    start.wait()
    answers[index] = queue.decide(request_id, decision)


def decide_all_at_once(queue, request_id, decisions):
    """Every decision made at the same moment, each on a thread of its own."""
    start = threading.Barrier(len(decisions))
    answers = [None] * len(decisions)

    threads = [
        threading.Thread(
            target=functools.partial(
                decide_of_decide_all_at_once, start, answers, queue, request_id
            ),
            args=(index, decision),
        )
        for index, decision in enumerate(decisions)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return answers


def test_request_decided_once_by_many_reps(queue, synthetic_db_path):
    request_id = add_request(synthetic_db_path)
    decisions = [RequestStatus.APPROVED, RequestStatus.REJECTED] * 6

    answers = decide_all_at_once(queue, request_id, decisions)

    won = [a for a in answers if "error" not in a]
    lost = [a for a in answers if "error" in a]
    assert len(won) == 1
    assert {a["error"] for a in lost} == {"ALREADY_DECIDED"}
    # The row holds the decision of the one that won, not a mix.
    assert status_of(synthetic_db_path, request_id) == won[0]["status"]


def test_senior_request_survives_many_clicks(queue, synthetic_db_path):
    request_id = add_request(synthetic_db_path, status=SENIOR, amount=900.0)

    answers = decide_all_at_once(
        queue, request_id, [RequestStatus.APPROVED, RequestStatus.REJECTED] * 4
    )

    assert {a["error"] for a in answers} == {"SENIOR_ONLY"}
    assert status_of(synthetic_db_path, request_id) == SENIOR


def close_of_ticket_closed_once_by_many_reps(start, answers, queue, ticket_id, index):
    start.wait()
    answers[index] = queue.close_ticket(ticket_id)


def test_ticket_closed_once_by_many_reps(queue, synthetic_db_path):
    ticket = add_ticket(synthetic_db_path)
    ticket_id = int(str(ticket).split("-")[-1])
    start = threading.Barrier(8)
    answers = [None] * 8

    threads = [
        threading.Thread(
            target=functools.partial(
                close_of_ticket_closed_once_by_many_reps,
                start,
                answers,
                queue,
                ticket_id,
            ),
            args=(i,),
        )
        for i in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sum("error" not in a for a in answers) == 1
