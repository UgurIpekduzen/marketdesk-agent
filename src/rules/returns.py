"""Return and cancel eligibility, decided by fixed rules (R0-R13).

No model is involved: the same order and reason always give the same
decision. The steps run in a fixed order and the first one that decides wins:

1. R0, R1: the order is not there for this customer   -> NOT_FOUND
2. R2-R5:  the order status rules out a return        -> see STATUS_DECISIONS
3. R11:    a return request already exists            -> DUPLICATE_REQUEST
4. R6, R7: the return window for the given reason     -> ELIGIBLE or
                                                         NOT_ELIGIBLE_WINDOW

An order that reaches step 4 then gets its flags and amounts, which never
change the decision:

5. R9:  freight refund flag for a late delivery
6. R8:  refund amount
7. R10: status a request would start in; R12: voucher share of the refund;
   R13: seller delay flag

Dates are compared as calendar days: the time of day is dropped and the
delivery day is day 0. "Today" is always passed in, never read from the
machine clock.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

import config


class DecisionCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    NOT_DELIVERED_CANCELLABLE = "NOT_DELIVERED_CANCELLABLE"
    IN_TRANSIT = "IN_TRANSIT"
    ALREADY_CLOSED = "ALREADY_CLOSED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE_WINDOW = "NOT_ELIGIBLE_WINDOW"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"


class ReturnReason(StrEnum):
    CHANGED_MIND = "changed_mind"
    LATE = "late"
    DAMAGED = "damaged"
    WRONG_ITEM = "wrong_item"


class RequestStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    PENDING_SENIOR = "PENDING_SENIOR"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# Return window in calendar days for each reason (R6, R7).
WINDOW_DAYS = {
    ReturnReason.CHANGED_MIND: config.RETURN_WINDOW_SHORT_DAYS,
    ReturnReason.LATE: config.RETURN_WINDOW_SHORT_DAYS,
    ReturnReason.DAMAGED: config.RETURN_WINDOW_LONG_DAYS,
    ReturnReason.WRONG_ITEM: config.RETURN_WINDOW_LONG_DAYS,
}

# Statuses that decide on their own, with the rule that says so (R2, R3,
# R4). "delivered" is not here: it needs the delivery date.
STATUS_DECISIONS = {
    "created": ("R2", DecisionCode.NOT_DELIVERED_CANCELLABLE),
    "approved": ("R2", DecisionCode.NOT_DELIVERED_CANCELLABLE),
    "invoiced": ("R2", DecisionCode.NOT_DELIVERED_CANCELLABLE),
    "processing": ("R2", DecisionCode.NOT_DELIVERED_CANCELLABLE),
    "shipped": ("R3", DecisionCode.IN_TRANSIT),
    "canceled": ("R4", DecisionCode.ALREADY_CLOSED),
    "unavailable": ("R4", DecisionCode.ALREADY_CLOSED),
}

# The rule that holds the return window for each reason.
WINDOW_RULES = {
    ReturnReason.CHANGED_MIND: "R6",
    ReturnReason.LATE: "R6",
    ReturnReason.DAMAGED: "R7",
    ReturnReason.WRONG_ITEM: "R7",
}

# A request in one of these states blocks a second one for the same order (R11).
BLOCKING_REQUEST_STATUSES = tuple(status.value for status in RequestStatus)

# Reasons whose refund always includes the freight (R7).
FREIGHT_INCLUDED_REASONS = (ReturnReason.DAMAGED, ReturnReason.WRONG_ITEM)

VOUCHER_PAYMENT_TYPE = "voucher"

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class OrderFacts:
    """What the rules need to know about one order."""

    status: str
    delivered_on: date | None
    has_blocking_request: bool
    estimated_on: date | None = None
    handed_to_carrier_on: date | None = None
    # One entry per item: the day the seller had to hand it over by.
    shipping_limits: tuple[date, ...] = ()
    # Amounts in BRL.
    price_total: Decimal = ZERO
    freight_total: Decimal = ZERO
    voucher_paid: Decimal = ZERO
    total_paid: Decimal = ZERO


@dataclass(frozen=True)
class ReturnDecision:
    code: DecisionCode
    # The rule that decided, for example "R6". A missing order and a foreign
    # one both say "R1".
    rule: str
    # Calendar days from delivery to today; None when no window was checked.
    days_since_delivery: int | None = None
    # R9: the delivery was late enough to earn the freight back.
    freight_refund: bool = False
    # R8, in BRL. With NOT_ELIGIBLE_WINDOW a positive amount is a
    # freight-only claim.
    refund_amount: Decimal = ZERO
    # R10: the status a request would start in; None when there is nothing
    # to refund.
    request_status: RequestStatus | None = None
    # R12: how refund_amount is split between voucher and the original
    # payment method.
    voucher_refund: Decimal = ZERO
    original_method_refund: Decimal = ZERO
    # R13: the seller handed an item to the carrier after its limit.
    seller_delay: bool = False


def to_money(value: Decimal) -> Decimal:
    """Round an amount to two decimal places."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def sum_money(values: list[float]) -> Decimal:
    """Add amounts stored as REAL without carrying float error into the sum."""
    return to_money(sum((Decimal(str(value)) for value in values), ZERO))


def to_calendar_day(text: str | None) -> date | None:
    """Turn a stored timestamp into its calendar day; empty or NULL is None."""
    if not text:
        return None
    return date.fromisoformat(text[:10])


def load_order_facts(
    conn: sqlite3.Connection, order_id: str, customer_unique_id: str
) -> OrderFacts | None:
    """Read one order of the given customer, or None.

    An order that does not exist and an order of another customer both give
    None, from the same query, so the caller cannot tell them apart (R0, R1).
    """
    row = conn.execute(
        "SELECT o.order_status, o.order_delivered_customer_date, "
        "o.order_estimated_delivery_date, o.order_delivered_carrier_date "
        "FROM orders AS o "
        "JOIN customers AS c ON c.customer_id = o.customer_id "
        "WHERE o.order_id = ? AND c.customer_unique_id = ?",
        (order_id, customer_unique_id),
    ).fetchone()
    if row is None:
        return None
    status, delivered_text, estimated_text, carrier_text = row

    placeholders = ", ".join("?" for _ in BLOCKING_REQUEST_STATUSES)
    blocking_requests = conn.execute(
        "SELECT COUNT(*) FROM return_requests "
        f"WHERE order_id = ? AND status IN ({placeholders})",
        (order_id, *BLOCKING_REQUEST_STATUSES),
    ).fetchone()[0]

    items = conn.execute(
        "SELECT price, freight_value, shipping_limit_date "
        "FROM order_items WHERE order_id = ?",
        (order_id,),
    ).fetchall()
    payments = conn.execute(
        "SELECT payment_type, payment_value FROM order_payments WHERE order_id = ?",
        (order_id,),
    ).fetchall()
    shipping_limits = [to_calendar_day(limit_text) for _, _, limit_text in items]

    return OrderFacts(
        status=status,
        delivered_on=to_calendar_day(delivered_text),
        has_blocking_request=blocking_requests > 0,
        estimated_on=to_calendar_day(estimated_text),
        handed_to_carrier_on=to_calendar_day(carrier_text),
        shipping_limits=tuple(day for day in shipping_limits if day is not None),
        price_total=sum_money([price for price, _, _ in items]),
        freight_total=sum_money([freight for _, freight, _ in items]),
        voucher_paid=sum_money(
            [value for kind, value in payments if kind == VOUCHER_PAYMENT_TYPE]
        ),
        total_paid=sum_money([value for _, value in payments]),
    )


def evaluate(
    facts: OrderFacts | None,
    reason: ReturnReason,
    today: date = config.SIMULATED_TODAY,
) -> ReturnDecision:
    """Decide whether the order can be returned for the given reason."""
    # Step 1 (R0, R1).
    if facts is None:
        return ReturnDecision(DecisionCode.NOT_FOUND, "R1")

    # Step 2 (R2-R5).
    if facts.status in STATUS_DECISIONS:
        rule, code = STATUS_DECISIONS[facts.status]
        return ReturnDecision(code, rule)
    if facts.status != "delivered" or facts.delivered_on is None:
        # R5, and any status the rules do not know: a person decides.
        return ReturnDecision(DecisionCode.NEEDS_HUMAN, "R5")
    if facts.delivered_on > today:
        # R3: marked delivered, but that day has not come yet.
        return ReturnDecision(DecisionCode.IN_TRANSIT, "R3")

    # Step 3 (R11).
    if facts.has_blocking_request:
        return ReturnDecision(DecisionCode.DUPLICATE_REQUEST, "R11")

    # Step 4 (R6, R7). The last day of the window is still inside it.
    days_since_delivery = (today - facts.delivered_on).days
    if days_since_delivery <= WINDOW_DAYS[reason]:
        code = DecisionCode.ELIGIBLE
    else:
        code = DecisionCode.NOT_ELIGIBLE_WINDOW

    # Step 5 (R9): delivered at least this many days after the estimate.
    freight_refund = (
        facts.estimated_on is not None
        and (facts.delivered_on - facts.estimated_on).days
        >= config.FREIGHT_REFUND_DELAY_DAYS
    )

    # Step 6 (R8).
    if code == DecisionCode.ELIGIBLE:
        refund_amount = facts.price_total
        if reason in FREIGHT_INCLUDED_REASONS or freight_refund:
            refund_amount += facts.freight_total
    elif freight_refund and days_since_delivery <= config.RETURN_WINDOW_LONG_DAYS:
        # Too late to return the items, still in time to claim the freight.
        refund_amount = facts.freight_total
    else:
        refund_amount = ZERO

    # Step 7 (R10): above the threshold a senior has to approve.
    if refund_amount == ZERO:
        request_status = None
    elif refund_amount > config.APPROVAL_THRESHOLD_BRL:
        request_status = RequestStatus.PENDING_SENIOR
    else:
        request_status = RequestStatus.PENDING_REVIEW

    # R12: the voucher's share of the payment goes back as voucher.
    if facts.total_paid > ZERO:
        voucher_refund = to_money(refund_amount * facts.voucher_paid / facts.total_paid)
    else:
        voucher_refund = ZERO

    # R13: one item handed over after its limit is enough.
    seller_delay = facts.handed_to_carrier_on is not None and any(
        facts.handed_to_carrier_on > limit for limit in facts.shipping_limits
    )

    return ReturnDecision(
        code=code,
        rule=WINDOW_RULES[reason],
        days_since_delivery=days_since_delivery,
        freight_refund=freight_refund,
        refund_amount=refund_amount,
        request_status=request_status,
        voucher_refund=voucher_refund,
        original_method_refund=refund_amount - voucher_refund,
        seller_delay=seller_delay,
    )


def check_return(
    conn: sqlite3.Connection,
    order_id: str,
    customer_unique_id: str,
    reason: str,
    today: date = config.SIMULATED_TODAY,
) -> ReturnDecision:
    """Load the order and decide. Raises ValueError for an unknown reason."""
    return evaluate(
        load_order_facts(conn, order_id, customer_unique_id),
        ReturnReason(reason),
        today,
    )
