"""Tests for the return eligibility function, on the synthetic database.

The rules themselves are tested in test_returns.py; these tests cover what
the function adds: the session, the alias and the shape of the output.
"""

import inspect
import json
import re

import pytest

from src import messages
from src.tools.eligibility import RETURN_REASONS, check_return_eligibility
from src.tools.orders import get_order_status
from src.tools.session import Session
from tests.synthetic_data import ALICE, BOB

NOT_FOUND = {"error": "NOT_FOUND", "message": messages.ORDER_NOT_FOUND}
REAL_SHAPED_ORDER_ID = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"


@pytest.fixture
def alice():
    return Session(ALICE)


def test_eligible_order(synthetic_db, alice):
    assert check_return_eligibility(alice, synthetic_db, "o_voucher", "damaged") == {
        "order": "SIP-1",
        "reason": "damaged",
        "decision": "ELIGIBLE",
        "rule": "R7",
        "days_since_delivery": 7,
        "refund_amount": "200.00",
        "refund_amount_text": "200,00 BRL",
        "freight_refund": False,
        "freight_included": True,
        "freight_only_claim": False,
        "request_status": "PENDING_REVIEW",
        "voucher_refund": "50.00",
        "voucher_refund_text": "50,00 BRL",
        "original_method_refund": "150.00",
        "original_method_refund_text": "150,00 BRL",
        "seller_delay": False,
    }


def test_order_that_cannot_be_returned_yet(synthetic_db, alice):
    assert check_return_eligibility(alice, synthetic_db, "o_shipped", "late") == {
        "order": "SIP-1",
        "reason": "late",
        "decision": "IN_TRANSIT",
        "rule": "R3",
        "days_since_delivery": None,
        "refund_amount": "0.00",
        "refund_amount_text": "0,00 BRL",
        "freight_refund": False,
        "freight_included": False,
        "freight_only_claim": False,
        "request_status": None,
        "voucher_refund": "0.00",
        "voucher_refund_text": "0,00 BRL",
        "original_method_refund": "0.00",
        "original_method_refund_text": "0,00 BRL",
        "seller_delay": False,
    }


@pytest.mark.parametrize(
    ("order", "reason", "freight_included", "freight_refund"),
    [
        # Damaged or wrong item: the freight is in the refund, though
        # freight_refund (the late-delivery refund) is false.
        ("o_day14", "damaged", True, False),
        ("o_day14", "wrong_item", True, False),
        # Late delivery inside the window.
        ("o_late_10", "late", True, True),
        ("o_late_10", "changed_mind", True, True),
        # Changed mind on an order that was on time: items only.
        ("o_day14", "changed_mind", False, False),
        # Only the freight can be claimed.
        ("o_late_freight_only", "changed_mind", True, True),
        # Nothing refunded, nothing included.
        ("o_late_day31", "late", False, False),
        ("o_shipped", "damaged", False, False),
    ],
)
def test_freight_included_tells_whether_the_freight_is_in_the_refund(
    synthetic_db, alice, order, reason, freight_included, freight_refund
):
    answer = check_return_eligibility(alice, synthetic_db, order, reason)

    assert answer["freight_included"] is freight_included
    assert answer["freight_refund"] is freight_refund


def test_the_description_tells_what_the_two_freight_fields_mean():
    doc = inspect.cleandoc(check_return_eligibility.__doc__)

    assert "freight_included is true when the freight is part of" in doc
    # The limit of the tool framework for a description.
    assert len(doc) <= 1024
    assert "freight_refund is true only for a late-delivery refund" in doc


def test_late_delivery_inside_the_window_refunds_the_freight_too(synthetic_db, alice):
    answer = check_return_eligibility(alice, synthetic_db, "o_late_10", "late")

    assert answer["decision"] == "ELIGIBLE"
    assert answer["refund_amount"] == "115.00"
    assert answer["freight_refund"] is True
    assert answer["freight_only_claim"] is False


def test_freight_only_claim(synthetic_db, alice):
    answer = check_return_eligibility(
        alice, synthetic_db, "o_late_freight_only", "changed_mind"
    )

    assert answer["decision"] == "NOT_ELIGIBLE_WINDOW"
    assert answer["refund_amount"] == "15.00"
    assert answer["freight_refund"] is True
    assert answer["freight_only_claim"] is True
    assert answer["request_status"] == "PENDING_REVIEW"


def test_late_delivery_after_every_window_promises_nothing(synthetic_db, alice):
    # The rule engine still flags the delay; the output must not.
    answer = check_return_eligibility(alice, synthetic_db, "o_late_day31", "late")

    assert answer["decision"] == "NOT_ELIGIBLE_WINDOW"
    assert answer["refund_amount"] == "0.00"
    assert answer["freight_refund"] is False
    assert answer["freight_only_claim"] is False
    assert answer["request_status"] is None


def test_seller_delay_is_passed_on(synthetic_db, alice):
    answer = check_return_eligibility(alice, synthetic_db, "o_seller_late", "late")

    assert answer["seller_delay"] is True


def test_alias_from_an_earlier_answer_is_accepted(synthetic_db, alice):
    alias = get_order_status(alice, synthetic_db, "o_day15")["order"]

    by_alias = check_return_eligibility(alice, synthetic_db, alias, "changed_mind")
    by_number = check_return_eligibility(alice, synthetic_db, "o_day15", "changed_mind")

    assert by_alias == by_number
    assert by_alias["order"] == alias
    assert by_alias["decision"] == "NOT_ELIGIBLE_WINDOW"


def test_foreign_missing_and_unknown_alias_give_the_same_answer(synthetic_db, alice):
    answers = [
        check_return_eligibility(alice, synthetic_db, order_ref, "damaged")
        for order_ref in ("o_other_customer", "o_does_not_exist", "SIP-7")
    ]

    assert answers == [NOT_FOUND] * 3


def test_not_found_is_the_same_answer_as_in_the_order_lookup(synthetic_db, alice):
    assert check_return_eligibility(
        alice, synthetic_db, "o_other_customer", "damaged"
    ) == get_order_status(alice, synthetic_db, "o_other_customer")


def test_alias_of_another_session_is_not_found(synthetic_db, alice):
    alias = get_order_status(alice, synthetic_db, "o_day14")["order"]

    answer = check_return_eligibility(Session(BOB), synthetic_db, alias, "damaged")

    assert answer == NOT_FOUND


@pytest.mark.parametrize("order_ref", ["o_day14", "o_other_customer"])
def test_unknown_reason_is_refused_with_the_allowed_values(
    synthetic_db, alice, order_ref
):
    # The same refusal whether or not the order is the customer's own.
    answer = check_return_eligibility(alice, synthetic_db, order_ref, "too_small")

    assert answer["error"] == "INVALID_REASON"
    for reason in RETURN_REASONS:
        assert reason in answer["message"]


@pytest.mark.parametrize("order_ref", ["o_day14", "o_other_customer"])
def test_missing_reason_is_asked_for_and_nothing_is_decided(
    synthetic_db, alice, order_ref
):
    # The same answer whether or not the order is the customer's own.
    answer = check_return_eligibility(alice, synthetic_db, order_ref)

    assert answer == {
        "error": "REASON_REQUIRED",
        "message": messages.RETURN_REASON_REQUIRED,
    }


def test_checking_writes_nothing(synthetic_db, alice):
    before = synthetic_db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]

    check_return_eligibility(alice, synthetic_db, "o_day14", "changed_mind")

    after = synthetic_db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]
    assert synthetic_db.total_changes == 0
    assert after == before


def test_output_holds_no_raw_id_city_or_zip_code(synthetic_db, alice):
    for table in ("orders", "order_items", "order_payments"):
        synthetic_db.execute(
            f"UPDATE {table} SET order_id = ? WHERE order_id = 'o_day14'",
            (REAL_SHAPED_ORDER_ID,),
        )

    outputs = json.dumps(
        [
            check_return_eligibility(alice, synthetic_db, REAL_SHAPED_ORDER_ID, reason)
            for reason in RETURN_REASONS
        ]
    )

    assert '"decision": "ELIGIBLE"' in outputs
    assert re.search(r"[0-9a-f]{32}", outputs) is None
    for forbidden in (ALICE, "c_o_", "o_day", "sao paulo", "01310"):
        assert forbidden not in outputs
