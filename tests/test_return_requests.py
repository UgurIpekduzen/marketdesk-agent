"""Tests for opening a return request, on the synthetic database.

The synthetic database starts with two requests (see RETURN_REQUESTS in
tests/synthetic_data.py); "nothing written" means it still has exactly two.
"""

import json
import re

import pytest

from src import messages
from src.tools.eligibility import check_return_eligibility
from src.tools.return_requests import create_return_request
from src.tools.session import Session
from tests.synthetic_data import ALICE, BOB

EXISTING_REQUESTS = 2
OTHER_TABLES = (
    "orders",
    "customers",
    "order_items",
    "order_payments",
    "order_reviews",
    "products",
    "sellers",
    "geolocation",
    "product_category_name_translation",
)


@pytest.fixture
def alice():
    return Session(ALICE)


def request_count(conn):
    return conn.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]


def new_requests(conn):
    return conn.execute(
        "SELECT order_id, customer_unique_id, reason, refund_amount, status, "
        "created_at FROM return_requests WHERE id > ? ORDER BY id",
        (EXISTING_REQUESTS,),
    ).fetchall()


def approve_and_create(session, conn, order_ref, reason, amount):
    """Do what the user interface does when the person says yes."""
    first = create_return_request(session, conn, order_ref, reason, amount)
    assert first["error"] == "APPROVAL_REQUIRED"
    token = session.approvals.approve()
    return create_return_request(session, conn, order_ref, reason, amount, token)


# --- Without approval ---------------------------------------------------


def test_unapproved_call_writes_nothing(synthetic_db, alice):
    answer = create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")

    assert answer == {
        "error": "APPROVAL_REQUIRED",
        "message": messages.APPROVAL_REQUIRED,
        "order": "SIP-1",
        "reason": "damaged",
        "refund_amount": "115.00",
        "refund_amount_text": "115,00 BRL",
        "request_status": "PENDING_REVIEW",
    }
    assert request_count(synthetic_db) == EXISTING_REQUESTS
    assert synthetic_db.total_changes == 0


@pytest.mark.parametrize("made_up", ["approved", "onaylandı", "true", "SIP-1", ""])
def test_made_up_token_writes_nothing(synthetic_db, alice, made_up):
    create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")

    answer = create_return_request(
        alice, synthetic_db, "o_day14", "damaged", "115.00", made_up
    )

    assert answer["error"] == "APPROVAL_REQUIRED"
    assert request_count(synthetic_db) == EXISTING_REQUESTS


def test_repeated_calls_are_not_approval(synthetic_db, alice):
    answers = [
        create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")
        for _ in range(5)
    ]

    assert {answer["error"] for answer in answers} == {"APPROVAL_REQUIRED"}
    assert request_count(synthetic_db) == EXISTING_REQUESTS


def test_token_fits_only_its_own_order(synthetic_db, alice):
    create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")
    token = alice.approvals.approve()

    answer = create_return_request(
        alice, synthetic_db, "o_two_items", "damaged", "165.00", token
    )

    assert answer["error"] == "APPROVAL_REQUIRED"
    assert request_count(synthetic_db) == EXISTING_REQUESTS


def test_token_does_not_cover_another_reason(synthetic_db, alice):
    # Approved as changed_mind (100.00); damaged would refund 115.00.
    create_return_request(alice, synthetic_db, "o_day14", "changed_mind", "100.00")
    token = alice.approvals.approve()

    answer = create_return_request(
        alice, synthetic_db, "o_day14", "damaged", "115.00", token
    )

    assert answer["error"] == "APPROVAL_REQUIRED"
    assert request_count(synthetic_db) == EXISTING_REQUESTS


def test_other_session_token_writes_nothing(synthetic_db, alice):
    other_session = Session(ALICE)
    create_return_request(other_session, synthetic_db, "o_day14", "damaged", "115.00")
    token = other_session.approvals.approve()

    answer = create_return_request(
        alice, synthetic_db, "o_day14", "damaged", "115.00", token
    )

    assert answer["error"] == "APPROVAL_REQUIRED"
    assert request_count(synthetic_db) == EXISTING_REQUESTS


def test_refusal_drops_the_waiting_request(synthetic_db, alice):
    create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")

    create_return_request(alice, synthetic_db, "o_shipped", "late", "115.00")

    with pytest.raises(LookupError):
        alice.approvals.approve()


# --- With approval ------------------------------------------------------


def test_approved_call_writes_one_row(synthetic_db, alice):
    answer = approve_and_create(alice, synthetic_db, "o_day14", "damaged", "115.00")

    assert answer == {
        "return_request_id": 3,
        "message": messages.RETURN_REQUEST_CREATED,
        "order": "SIP-1",
        "reason": "damaged",
        "refund_amount": "115.00",
        "refund_amount_text": "115,00 BRL",
        "status": "PENDING_REVIEW",
    }
    assert [tuple(row) for row in new_requests(synthetic_db)] == [
        ("o_day14", ALICE, "damaged", 115.0, "PENDING_REVIEW", "2018-09-01 00:00:00")
    ]


@pytest.mark.parametrize(
    ("order_id", "reason", "amount", "status"),
    [
        ("o_amount_500", "changed_mind", "500.00", "PENDING_REVIEW"),
        ("o_amount_over", "changed_mind", "500.01", "PENDING_SENIOR"),
        ("o_amount_500", "damaged", "520.00", "PENDING_SENIOR"),
    ],
)
def test_status_follows_the_refund_amount(
    synthetic_db, alice, order_id, reason, amount, status
):
    answer = approve_and_create(alice, synthetic_db, order_id, reason, amount)

    assert answer["status"] == status
    assert new_requests(synthetic_db)[0]["status"] == status


def test_freight_only_claim_can_be_opened(synthetic_db, alice):
    answer = approve_and_create(
        alice, synthetic_db, "o_late_freight_only", "changed_mind", "15.00"
    )

    assert answer["status"] == "PENDING_REVIEW"
    assert new_requests(synthetic_db)[0]["refund_amount"] == 15.0


def test_numeric_amount_is_accepted(synthetic_db, alice):
    answer = approve_and_create(alice, synthetic_db, "o_day14", "damaged", 115.0)

    assert answer["refund_amount"] == "115.00"


def test_write_touches_only_requests_table(synthetic_db, alice):
    def snapshot():
        return {
            table: synthetic_db.execute(f"SELECT * FROM {table}").fetchall()
            for table in OTHER_TABLES
        }

    before = snapshot()

    approve_and_create(alice, synthetic_db, "o_day14", "damaged", "115.00")

    assert snapshot() == before
    assert synthetic_db.total_changes == 1


def test_approval_uses_earlier_check_alias(synthetic_db, alice):
    checked = check_return_eligibility(alice, synthetic_db, "o_day14", "damaged")

    answer = approve_and_create(
        alice, synthetic_db, checked["order"], "damaged", checked["refund_amount"]
    )

    assert answer["order"] == checked["order"]
    assert answer["status"] == checked["request_status"]


# --- R11: a second request ----------------------------------------------


def test_second_request_is_a_duplicate(synthetic_db, alice):
    approve_and_create(alice, synthetic_db, "o_day14", "damaged", "115.00")

    again = create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")

    assert again == {
        "error": "DUPLICATE_REQUEST",
        "message": messages.DUPLICATE_REQUEST,
        "order": "SIP-1",
    }
    assert len(new_requests(synthetic_db)) == 1


def test_token_cannot_be_used_twice(synthetic_db, alice):
    create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")
    token = alice.approvals.approve()
    create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00", token)
    synthetic_db.execute(
        "DELETE FROM return_requests WHERE id > ?", (EXISTING_REQUESTS,)
    )

    again = create_return_request(
        alice, synthetic_db, "o_day14", "damaged", "115.00", token
    )

    assert again["error"] == "APPROVAL_REQUIRED"
    assert request_count(synthetic_db) == EXISTING_REQUESTS


def test_late_request_still_blocks(synthetic_db, alice):
    # Approved, but another request for the order is written before the call.
    create_return_request(alice, synthetic_db, "o_day14", "damaged", "115.00")
    token = alice.approvals.approve()
    order_id, reason, amount = "o_day14", "damaged", "115.00"
    second_session = Session(ALICE)
    approve_and_create(second_session, synthetic_db, order_id, reason, amount)

    answer = create_return_request(alice, synthetic_db, order_id, reason, amount, token)

    assert answer["error"] == "DUPLICATE_REQUEST"
    assert len(new_requests(synthetic_db)) == 1


def test_existing_request_is_a_duplicate(synthetic_db, alice):
    answer = create_return_request(
        alice, synthetic_db, "o_duplicate", "changed_mind", "100.00"
    )

    assert answer["error"] == "DUPLICATE_REQUEST"
    assert alice.approvals.awaiting is None


# --- Requests that are refused before any approval ----------------------


@pytest.mark.parametrize(
    ("order_id", "reason", "code"),
    [
        ("o_processing", "changed_mind", "NOT_DELIVERED_CANCELLABLE"),
        ("o_shipped", "late", "IN_TRANSIT"),
        ("o_delivered_future", "late", "IN_TRANSIT"),
        ("o_canceled", "changed_mind", "ALREADY_CLOSED"),
        ("o_no_delivery_date", "damaged", "NEEDS_HUMAN"),
        ("o_day15", "changed_mind", "NOT_ELIGIBLE_WINDOW"),
        ("o_late_day31", "late", "NOT_ELIGIBLE_WINDOW"),
    ],
)
def test_refused_order_never_gets_a_card(synthetic_db, alice, order_id, reason, code):
    answer = create_return_request(alice, synthetic_db, order_id, reason, "100.00")

    assert answer == {
        "error": code,
        "message": messages.RETURN_NOT_POSSIBLE,
        "order": "SIP-1",
    }
    assert alice.approvals.awaiting is None
    assert request_count(synthetic_db) == EXISTING_REQUESTS


@pytest.mark.parametrize("amount", ["115.01", "114.99", "1000", "0", "-115.00"])
def test_wrong_amount_is_refused(synthetic_db, alice, amount):
    answer = create_return_request(alice, synthetic_db, "o_day14", "damaged", amount)

    assert answer["error"] == "AMOUNT_MISMATCH"
    assert answer["refund_amount"] == "115.00"
    assert alice.approvals.awaiting is None


@pytest.mark.parametrize("amount", ["a lot", "", "115,00"])
def test_non_numeric_amount_is_refused(synthetic_db, alice, amount):
    answer = create_return_request(alice, synthetic_db, "o_day14", "damaged", amount)

    assert answer == {"error": "INVALID_AMOUNT", "message": messages.INVALID_AMOUNT}


def test_unknown_reason_is_refused(synthetic_db, alice):
    answer = create_return_request(alice, synthetic_db, "o_day14", "too_small", "100")

    assert answer["error"] == "INVALID_REASON"


def test_foreign_and_missing_not_found(synthetic_db, alice):
    not_found = {"error": "NOT_FOUND", "message": messages.ORDER_NOT_FOUND}

    foreign = create_return_request(
        alice, synthetic_db, "o_other_customer", "damaged", "115.00"
    )
    missing = create_return_request(
        alice, synthetic_db, "o_does_not_exist", "damaged", "115.00"
    )

    assert foreign == missing == not_found
    assert alice.approvals.awaiting is None


def test_foreign_order_refused_with_token(synthetic_db, alice):
    bob = Session(BOB)
    create_return_request(bob, synthetic_db, "o_other_customer", "damaged", "115.00")
    token = bob.approvals.approve()

    answer = create_return_request(
        alice, synthetic_db, "o_other_customer", "damaged", "115.00", token
    )

    assert answer["error"] == "NOT_FOUND"
    assert request_count(synthetic_db) == EXISTING_REQUESTS


# --- What the outputs may contain ---------------------------------------


def test_outputs_hold_no_raw_id_or_token(synthetic_db, alice):
    real_shaped = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
    for table in ("orders", "order_items", "order_payments"):
        synthetic_db.execute(
            f"UPDATE {table} SET order_id = ? WHERE order_id = 'o_day14'",
            (real_shaped,),
        )

    asked = create_return_request(alice, synthetic_db, real_shaped, "damaged", "115.00")
    token = alice.approvals.approve()
    created = create_return_request(
        alice, synthetic_db, real_shaped, "damaged", "115.00", token
    )
    outputs = json.dumps([asked, created], ensure_ascii=False)

    assert created["status"] == "PENDING_REVIEW"
    assert re.search(r"[0-9a-f]{32}", outputs) is None
    assert token not in outputs
    assert ALICE not in outputs
