"""Tests for the return rules, on the synthetic database.

Order ids say which case an order stands for; see tests/synthetic_data.py.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.rules.returns import (
    DecisionCode,
    OrderFacts,
    RequestStatus,
    ReturnDecision,
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


# --- Step 5: R9 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("order_id", "flag"),
    [
        ("o_late_10", True),  # exactly 10 days after the estimate
        ("o_late_9", False),  # one day short
        ("o_day0", False),  # delivered before the estimate
    ],
)
def test_freight_refund_flag_needs_ten_days_of_delay(synthetic_db, order_id, flag):
    assert decide(synthetic_db, order_id).freight_refund is flag


def test_freight_refund_flag_stays_after_every_window(synthetic_db):
    # 31 days after delivery: the delay is a fact, but nothing is refunded.
    decision = decide(synthetic_db, "o_late_day31")

    assert decision.code == DecisionCode.NOT_ELIGIBLE_WINDOW
    assert decision.freight_refund is True
    assert decision.refund_amount == Decimal("0.00")
    assert decision.request_status is None


# --- Step 6: R8 ---------------------------------------------------------


@pytest.mark.parametrize(
    ("order_id", "reason", "code", "amount"),
    [
        # Eligible: item prices; freight on top for R7 reasons or an R9 flag.
        ("o_day14", "changed_mind", DecisionCode.ELIGIBLE, "100.00"),
        ("o_day14", "damaged", DecisionCode.ELIGIBLE, "115.00"),
        ("o_day14", "wrong_item", DecisionCode.ELIGIBLE, "115.00"),
        ("o_late_10", "changed_mind", DecisionCode.ELIGIBLE, "115.00"),
        ("o_late_10", "late", DecisionCode.ELIGIBLE, "115.00"),
        ("o_late_9", "late", DecisionCode.ELIGIBLE, "100.00"),
        ("o_two_items", "changed_mind", DecisionCode.ELIGIBLE, "150.00"),
        ("o_two_items", "damaged", DecisionCode.ELIGIBLE, "165.00"),
        # Outside the short window with an R9 flag: freight only, up to day 30.
        (
            "o_late_freight_only",
            "changed_mind",
            DecisionCode.NOT_ELIGIBLE_WINDOW,
            "15.00",
        ),
        ("o_late_day30", "late", DecisionCode.NOT_ELIGIBLE_WINDOW, "15.00"),
        ("o_late_day31", "late", DecisionCode.NOT_ELIGIBLE_WINDOW, "0.00"),
        # The same late order inside the long window: a full refund.
        ("o_late_freight_only", "damaged", DecisionCode.ELIGIBLE, "115.00"),
        # Outside the window without a flag: nothing.
        ("o_day15", "changed_mind", DecisionCode.NOT_ELIGIBLE_WINDOW, "0.00"),
        ("o_day31", "damaged", DecisionCode.NOT_ELIGIBLE_WINDOW, "0.00"),
    ],
)
def test_refund_amount(synthetic_db, order_id, reason, code, amount):
    decision = decide(synthetic_db, order_id, reason)

    assert decision.code == code
    assert decision.refund_amount == Decimal(amount)


@pytest.mark.parametrize(
    "order_id",
    [
        "o_does_not_exist",
        "o_created",
        "o_shipped",
        "o_delivered_future",
        "o_canceled",
        "o_no_delivery_date",
        "o_duplicate",
    ],
)
def test_other_decisions_carry_no_amount_or_flag(synthetic_db, order_id):
    decision = decide(synthetic_db, order_id)

    assert decision == ReturnDecision(decision.code, decision.rule)


def test_amounts_are_exact_to_the_cent():
    # 0.10 + 0.20 is 0.30000000000000004 as floats.
    facts = facts_delivered_on(
        date(2018, 8, 25), price_total=Decimal("0.10"), freight_total=Decimal("0.20")
    )

    decision = evaluate(facts, ReturnReason.DAMAGED, TODAY)

    assert decision.refund_amount == Decimal("0.30")


# --- Step 7: R10 --------------------------------------------------------


@pytest.mark.parametrize(
    ("order_id", "reason", "amount", "status"),
    [
        # Exactly 500 is not above the threshold.
        ("o_amount_500", "changed_mind", "500.00", RequestStatus.PENDING_REVIEW),
        ("o_amount_over", "changed_mind", "500.01", RequestStatus.PENDING_SENIOR),
        # The threshold applies to the amount with freight when it is included.
        ("o_amount_500", "damaged", "520.00", RequestStatus.PENDING_SENIOR),
        # A freight-only claim is a request too.
        ("o_late_freight_only", "changed_mind", "15.00", RequestStatus.PENDING_REVIEW),
    ],
)
def test_request_status_by_refund_amount(
    synthetic_db, order_id, reason, amount, status
):
    decision = decide(synthetic_db, order_id, reason)

    assert decision.refund_amount == Decimal(amount)
    assert decision.request_status == status


# --- Step 7: R12 --------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "amount", "voucher", "original"),
    [
        # A quarter of the payment (50 of 200) was a voucher.
        ("changed_mind", "180.00", "45.00", "135.00"),
        ("damaged", "200.00", "50.00", "150.00"),
    ],
)
def test_voucher_share_of_the_refund(synthetic_db, reason, amount, voucher, original):
    decision = decide(synthetic_db, "o_voucher", reason)

    assert decision.refund_amount == Decimal(amount)
    assert decision.voucher_refund == Decimal(voucher)
    assert decision.original_method_refund == Decimal(original)


def test_refund_without_a_voucher_goes_to_the_original_method(synthetic_db):
    decision = decide(synthetic_db, "o_day14")

    assert decision.voucher_refund == Decimal("0.00")
    assert decision.original_method_refund == Decimal("100.00")


def test_voucher_split_always_adds_up_to_the_refund():
    # A third of 100.00 cannot be split evenly: 33.33 + 66.67.
    facts = facts_delivered_on(
        date(2018, 8, 25),
        price_total=Decimal("100.00"),
        voucher_paid=Decimal("10.00"),
        total_paid=Decimal("30.00"),
    )

    decision = evaluate(facts, ReturnReason.CHANGED_MIND, TODAY)

    assert decision.voucher_refund == Decimal("33.33")
    assert decision.original_method_refund == Decimal("66.67")


def test_order_without_payment_rows_has_no_voucher_share():
    facts = facts_delivered_on(date(2018, 8, 25), price_total=Decimal("100.00"))

    decision = evaluate(facts, ReturnReason.CHANGED_MIND, TODAY)

    assert decision.voucher_refund == Decimal("0.00")
    assert decision.original_method_refund == Decimal("100.00")


# --- Step 7: R13 --------------------------------------------------------


@pytest.mark.parametrize(
    ("order_id", "flag"),
    [
        ("o_seller_late", True),  # handed over two days after the limit
        ("o_seller_late_one_item", True),  # only the second item's limit missed
        ("o_seller_same_day", False),  # on the limit day, later in the day
        ("o_day14", False),  # handed over before the limit
    ],
)
def test_seller_delay_flag(synthetic_db, order_id, flag):
    assert decide(synthetic_db, order_id).seller_delay is flag


def test_seller_delay_does_not_change_the_decision_or_amount(synthetic_db):
    late = decide(synthetic_db, "o_seller_late")
    on_time = decide(synthetic_db, "o_late_9")

    assert (late.code, late.refund_amount) == (on_time.code, on_time.refund_amount)


# --- The rule behind a decision -----------------------------------------


@pytest.mark.parametrize(
    ("order_id", "reason", "rule"),
    [
        ("o_does_not_exist", "changed_mind", "R1"),
        ("o_other_customer", "changed_mind", "R1"),
        ("o_created", "changed_mind", "R2"),
        ("o_shipped", "changed_mind", "R3"),
        ("o_delivered_future", "changed_mind", "R3"),
        ("o_canceled", "changed_mind", "R4"),
        ("o_no_delivery_date", "changed_mind", "R5"),
        ("o_duplicate", "changed_mind", "R11"),
        ("o_day14", "changed_mind", "R6"),
        ("o_day15", "late", "R6"),
        ("o_day30", "damaged", "R7"),
        ("o_day31", "wrong_item", "R7"),
    ],
)
def test_decision_names_the_rule_that_decided(synthetic_db, order_id, reason, rule):
    assert decide(synthetic_db, order_id, reason).rule == rule


# --- Inputs -------------------------------------------------------------


def test_unknown_reason_is_rejected(synthetic_db):
    with pytest.raises(ValueError, match="no_longer_needed"):
        decide(synthetic_db, "o_day0", reason="no_longer_needed")


def test_delivery_timestamp_is_read_as_a_calendar_day(synthetic_db):
    # Stored as 2018-08-18 23:50:00.
    facts = load_order_facts(synthetic_db, "o_day14", ALICE)

    assert facts.delivered_on == date(2018, 8, 18)


def facts_delivered_on(day, **amounts):
    return OrderFacts(
        status="delivered", delivered_on=day, has_blocking_request=False, **amounts
    )
