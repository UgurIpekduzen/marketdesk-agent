"""The return eligibility check, as a function a tool can wrap.

The decision comes from the rule engine. This module only finds the order
for the customer in the session and turns the decision into plain output.
"""

import sqlite3
from datetime import date

import config
from src import messages
from src.formatting import format_money
from src.rules.returns import DecisionCode, ReturnReason, check_return
from src.tools.orders import NOT_FOUND
from src.tools.session import Session

RETURN_REASONS = tuple(reason.value for reason in ReturnReason)


def check_return_eligibility(
    session: Session,
    conn: sqlite3.Connection,
    order_ref: str,
    reason: str | None = None,
    today: date = config.SIMULATED_TODAY,
) -> dict:
    """Decide whether one order of the current customer can be returned.

    order_ref is the order alias from an earlier answer (for example SIP-1)
    or the order number the customer wrote. reason is why they want to
    return it: changed_mind, late, damaged or wrong_item. Leave reason out
    if the customer has not said why; never guess it.

    The decision comes from fixed rules and is final: report it, do not
    change it. decision is NOT_DELIVERED_CANCELLABLE, IN_TRANSIT,
    ALREADY_CLOSED, NEEDS_HUMAN, DUPLICATE_REQUEST, ELIGIBLE or
    NOT_ELIGIBLE_WINDOW; rule is the rule that decided. refund_amount (BRL)
    is what a request would refund; "0.00" means nothing can be refunded.
    freight_refund is true when the freight is refunded because the delivery
    was late. freight_only_claim is true when the items can no longer be
    returned but the freight can still be claimed. An unknown order answers
    {"error": "NOT_FOUND", "message": ...}.
    """
    if reason is None:
        # Asked before any order is looked up, so it says nothing about one.
        return {"error": "REASON_REQUIRED", "message": messages.RETURN_REASON_REQUIRED}
    if reason not in RETURN_REASONS:
        return {
            "error": "INVALID_REASON",
            "message": messages.INVALID_RETURN_REASON.format(
                allowed=", ".join(RETURN_REASONS)
            ),
        }

    order_id = session.order_id_for(order_ref)
    decision = check_return(conn, order_id, session.customer_unique_id, reason, today)
    if decision.code == DecisionCode.NOT_FOUND:
        return dict(NOT_FOUND)

    has_refund = decision.refund_amount > 0
    return {
        "order": session.alias_for(order_id),
        "reason": reason,
        "decision": decision.code.value,
        "rule": decision.rule,
        "days_since_delivery": decision.days_since_delivery,
        "refund_amount": str(decision.refund_amount),
        "refund_amount_text": format_money(str(decision.refund_amount)),
        # The rule engine flags every late delivery. Here the flag is shown
        # only while it still earns money, so it cannot be read as a promise.
        "freight_refund": decision.freight_refund and has_refund,
        "freight_only_claim": (
            decision.code == DecisionCode.NOT_ELIGIBLE_WINDOW and has_refund
        ),
        "request_status": (
            decision.request_status.value if decision.request_status else None
        ),
        "voucher_refund": str(decision.voucher_refund),
        "voucher_refund_text": format_money(str(decision.voucher_refund)),
        "original_method_refund": str(decision.original_method_refund),
        "original_method_refund_text": format_money(
            str(decision.original_method_refund)
        ),
        "seller_delay": decision.seller_delay,
    }
