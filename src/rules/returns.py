"""Return and cancel eligibility, decided by fixed rules (R0-R13).

No model is involved: the same order and reason always give the same
decision. The steps run in a fixed order and the first one that decides wins:

1. R0, R1: the order is not there for this customer   -> NOT_FOUND
2. R2-R5:  the order status rules out a return        -> see STATUS_DECISIONS
3. R11:    a return request already exists            -> DUPLICATE_REQUEST
4. R6, R7: the return window for the given reason     -> ELIGIBLE or
                                                         NOT_ELIGIBLE_WINDOW

Dates are compared as calendar days: the time of day is dropped and the
delivery day is day 0. "Today" is always passed in, never read from the
machine clock.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date
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


# Return window in calendar days for each reason (R6, R7).
WINDOW_DAYS = {
    ReturnReason.CHANGED_MIND: config.RETURN_WINDOW_SHORT_DAYS,
    ReturnReason.LATE: config.RETURN_WINDOW_SHORT_DAYS,
    ReturnReason.DAMAGED: config.RETURN_WINDOW_LONG_DAYS,
    ReturnReason.WRONG_ITEM: config.RETURN_WINDOW_LONG_DAYS,
}

# Statuses that decide on their own (R2, R3, R4). "delivered" is not here:
# it needs the delivery date.
STATUS_DECISIONS = {
    "created": DecisionCode.NOT_DELIVERED_CANCELLABLE,
    "approved": DecisionCode.NOT_DELIVERED_CANCELLABLE,
    "invoiced": DecisionCode.NOT_DELIVERED_CANCELLABLE,
    "processing": DecisionCode.NOT_DELIVERED_CANCELLABLE,
    "shipped": DecisionCode.IN_TRANSIT,
    "canceled": DecisionCode.ALREADY_CLOSED,
    "unavailable": DecisionCode.ALREADY_CLOSED,
}

# A request in one of these states blocks a second one for the same order (R11).
BLOCKING_REQUEST_STATUSES = ("PENDING_REVIEW", "PENDING_SENIOR", "APPROVED", "REJECTED")


@dataclass(frozen=True)
class OrderFacts:
    """What the rules need to know about one order."""

    status: str
    delivered_on: date | None
    has_blocking_request: bool


@dataclass(frozen=True)
class ReturnDecision:
    code: DecisionCode
    # Calendar days from delivery to today; None when no window was checked.
    days_since_delivery: int | None = None


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
        "SELECT o.order_status, o.order_delivered_customer_date "
        "FROM orders AS o "
        "JOIN customers AS c ON c.customer_id = o.customer_id "
        "WHERE o.order_id = ? AND c.customer_unique_id = ?",
        (order_id, customer_unique_id),
    ).fetchone()
    if row is None:
        return None
    status, delivered_text = row

    placeholders = ", ".join("?" for _ in BLOCKING_REQUEST_STATUSES)
    blocking_requests = conn.execute(
        "SELECT COUNT(*) FROM return_requests "
        f"WHERE order_id = ? AND status IN ({placeholders})",
        (order_id, *BLOCKING_REQUEST_STATUSES),
    ).fetchone()[0]

    return OrderFacts(
        status=status,
        delivered_on=to_calendar_day(delivered_text),
        has_blocking_request=blocking_requests > 0,
    )


def evaluate(
    facts: OrderFacts | None,
    reason: ReturnReason,
    today: date = config.SIMULATED_TODAY,
) -> ReturnDecision:
    """Decide whether the order can be returned for the given reason."""
    # Step 1 (R0, R1).
    if facts is None:
        return ReturnDecision(DecisionCode.NOT_FOUND)

    # Step 2 (R2-R5).
    if facts.status in STATUS_DECISIONS:
        return ReturnDecision(STATUS_DECISIONS[facts.status])
    if facts.status != "delivered" or facts.delivered_on is None:
        # R5, and any status the rules do not know: a person decides.
        return ReturnDecision(DecisionCode.NEEDS_HUMAN)
    if facts.delivered_on > today:
        # R3: marked delivered, but that day has not come yet.
        return ReturnDecision(DecisionCode.IN_TRANSIT)

    # Step 3 (R11).
    if facts.has_blocking_request:
        return ReturnDecision(DecisionCode.DUPLICATE_REQUEST)

    # Step 4 (R6, R7). The last day of the window is still inside it.
    days_since_delivery = (today - facts.delivered_on).days
    if days_since_delivery <= WINDOW_DAYS[reason]:
        code = DecisionCode.ELIGIBLE
    else:
        code = DecisionCode.NOT_ELIGIBLE_WINDOW
    return ReturnDecision(code, days_since_delivery)


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
