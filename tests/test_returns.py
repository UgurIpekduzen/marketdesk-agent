"""Tests for the return rules, on the synthetic database.

Order ids say which case an order stands for; see tests/synthetic_data.py.
"""

from datetime import date

import pytest

from src.rules.returns import (
    DecisionCode,
    OrderFacts,
    ReturnReason,
    check_return,
    evaluate,
    load_order_facts,
)
from tests.synthetic_data import ALICE, BOB

TODAY = date(2018, 9, 1)


def decide(conn, order_id, reason="changed_mind", customer=ALICE):
    return check_return(conn, order_id, customer, reason)


# --- Step 1: R0, R1 -----------------------------------------------------


def test_order_left_out_at_load_is_not_found(synthetic_db):
    assert decide(synthetic_db, "o_purchased_today").code == DecisionCode.NOT_FOUND


def test_order_of_another_customer_is_not_found(synthetic_db):
    assert decide(synthetic_db, "o_other_customer").code == DecisionCode.NOT_FOUND


def test_order_is_found_by_its_own_customer(synthetic_db):
    decision = decide(synthetic_db, "o_other_customer", customer=BOB)

    assert decision.code == DecisionCode.ELIGIBLE


def test_foreign_and_missing_orders_give_the_same_decision(synthetic_db):
    foreign = decide(synthetic_db, "o_other_customer")
    missing = decide(synthetic_db, "o_does_not_exist")

    assert foreign == missing


# --- Step 2: R2-R5 ------------------------------------------------------


@pytest.mark.parametrize(
    "order_id", ["o_created", "o_approved", "o_invoiced", "o_processing"]
)
def test_order_not_handed_over_yet_can_be_cancelled(synthetic_db, order_id):
    decision = decide(synthetic_db, order_id)

    assert decision.code == DecisionCode.NOT_DELIVERED_CANCELLABLE


def test_shipped_order_is_in_transit(synthetic_db):
    assert decide(synthetic_db, "o_shipped").code == DecisionCode.IN_TRANSIT


def test_order_delivered_after_today_is_in_transit(synthetic_db):
    # Delivery date 2018-09-05, four days after the simulated today.
    decision = decide(synthetic_db, "o_delivered_future")

    assert decision.code == DecisionCode.IN_TRANSIT


@pytest.mark.parametrize("order_id", ["o_canceled", "o_unavailable"])
def test_canceled_or_unavailable_order_is_closed(synthetic_db, order_id):
    assert decide(synthetic_db, order_id).code == DecisionCode.ALREADY_CLOSED


def test_delivered_order_without_delivery_date_needs_a_human(synthetic_db):
    decision = decide(synthetic_db, "o_no_delivery_date")

    assert decision.code == DecisionCode.NEEDS_HUMAN


def test_unknown_status_needs_a_human():
    facts = OrderFacts(
        status="lost", delivered_on=date(2018, 8, 25), has_blocking_request=False
    )

    decision = evaluate(facts, ReturnReason.CHANGED_MIND, TODAY)

    assert decision.code == DecisionCode.NEEDS_HUMAN


# --- Step 3: R11 --------------------------------------------------------


def test_second_request_for_the_same_order_is_a_duplicate(synthetic_db):
    assert decide(synthetic_db, "o_duplicate").code == DecisionCode.DUPLICATE_REQUEST


def test_rejected_request_still_blocks_a_second_one(synthetic_db):
    # Delivered 62 days ago: the duplicate check comes before the window.
    decision = decide(synthetic_db, "o_duplicate_old", reason="damaged")

    assert decision.code == DecisionCode.DUPLICATE_REQUEST


def test_request_in_another_state_does_not_block(synthetic_db):
    synthetic_db.execute(
        "UPDATE return_requests SET status = 'WITHDRAWN' WHERE order_id = 'o_duplicate'"
    )

    assert decide(synthetic_db, "o_duplicate").code == DecisionCode.ELIGIBLE


# --- Step 4: R6, R7 -----------------------------------------------------


@pytest.mark.parametrize(
    ("order_id", "reason", "days", "code"),
    [
        # R6: 14 days for changed_mind and late.
        ("o_day0", "changed_mind", 0, DecisionCode.ELIGIBLE),
        ("o_day14", "changed_mind", 14, DecisionCode.ELIGIBLE),
        ("o_day15", "changed_mind", 15, DecisionCode.NOT_ELIGIBLE_WINDOW),
        ("o_day14", "late", 14, DecisionCode.ELIGIBLE),
        ("o_day15", "late", 15, DecisionCode.NOT_ELIGIBLE_WINDOW),
        # R7: 30 days for damaged and wrong_item.
        ("o_day15", "damaged", 15, DecisionCode.ELIGIBLE),
        ("o_day30", "damaged", 30, DecisionCode.ELIGIBLE),
        ("o_day31", "damaged", 31, DecisionCode.NOT_ELIGIBLE_WINDOW),
        ("o_day30", "wrong_item", 30, DecisionCode.ELIGIBLE),
        ("o_day31", "wrong_item", 31, DecisionCode.NOT_ELIGIBLE_WINDOW),
    ],
)
def test_return_window_boundaries(synthetic_db, order_id, reason, days, code):
    decision = decide(synthetic_db, order_id, reason)

    assert decision.days_since_delivery == days
    assert decision.code == code


def test_today_is_a_parameter_not_the_clock():
    facts = facts_delivered_on(date(2018, 8, 18))

    one_day_later = evaluate(facts, ReturnReason.CHANGED_MIND, date(2018, 9, 2))

    assert one_day_later.days_since_delivery == 15
    assert one_day_later.code == DecisionCode.NOT_ELIGIBLE_WINDOW


def test_decisions_without_a_window_carry_no_day_count(synthetic_db):
    assert decide(synthetic_db, "o_shipped").days_since_delivery is None


# --- Inputs -------------------------------------------------------------


def test_unknown_reason_is_rejected(synthetic_db):
    with pytest.raises(ValueError, match="no_longer_needed"):
        decide(synthetic_db, "o_day0", reason="no_longer_needed")


def test_delivery_timestamp_is_read_as_a_calendar_day(synthetic_db):
    # Stored as 2018-08-18 23:50:00.
    facts = load_order_facts(synthetic_db, "o_day14", ALICE)

    assert facts.delivered_on == date(2018, 8, 18)


def facts_delivered_on(day):
    return OrderFacts(status="delivered", delivered_on=day, has_blocking_request=False)
