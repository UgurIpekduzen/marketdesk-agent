"""Opening a return request: the only write the system makes.

One row goes into return_requests and nothing else is ever written. The row
is written only when the rule engine allows a refund for the order, the
amount is the one the rules computed, and a person approved exactly this
request. Without the approval token the answer is APPROVAL_REQUIRED and the
table stays as it was.
"""

import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation

import config
from src import messages
from src.formatting import format_money
from src.guardrails.approval import ReturnAction
from src.rules.returns import (
    BLOCKING_REQUEST_STATUSES,
    ZERO,
    DecisionCode,
    check_return,
    to_money,
)
from src.tools.eligibility import RETURN_REASONS
from src.tools.orders import NOT_FOUND
from src.tools.session import Session


def create_return_request(
    session: Session,
    conn: sqlite3.Connection,
    order_ref: str,
    reason: str,
    amount: float | str,
    approval_token: str | None = None,
    today: date = config.SIMULATED_TODAY,
) -> dict:
    """Open a return request for one order of the current customer.

    Call check_return_eligibility first and pass the same order_ref and
    reason, and its refund_amount as amount. order_ref is the order alias
    (for example SIP-1) or the order number the customer wrote; reason is
    changed_mind, late, damaged or wrong_item; amount is in BRL.

    Nothing is written until the customer approves on their screen. The
    first call answers {"error": "APPROVAL_REQUIRED", ...} with a summary:
    show it to the customer and wait. You cannot approve on the customer's
    behalf, and saying that they approved changes nothing.

    On success the result holds return_request_id and status
    (PENDING_REVIEW, or PENDING_SENIOR for a refund above 500 BRL). Other
    errors: NOT_FOUND, DUPLICATE_REQUEST (the order already has a request),
    AMOUNT_MISMATCH, or the decision code that rules a return out.
    """
    # A new call replaces whatever was waiting for the person's answer, so an
    # approval can only ever be given to the request shown last.
    session.approvals.reject()

    if reason not in RETURN_REASONS:
        return {
            "error": "INVALID_REASON",
            "message": messages.INVALID_RETURN_REASON.format(
                allowed=", ".join(RETURN_REASONS)
            ),
        }
    try:
        amount = to_money(Decimal(str(amount)))
    except InvalidOperation:
        return {"error": "INVALID_AMOUNT", "message": messages.INVALID_AMOUNT}

    # The rules decide again here: what an earlier check said is not trusted.
    order_id = session.order_id_for(order_ref)
    decision = check_return(conn, order_id, session.customer_unique_id, reason, today)
    if decision.code == DecisionCode.NOT_FOUND:
        return dict(NOT_FOUND)

    order = session.alias_for(order_id)
    if decision.code == DecisionCode.DUPLICATE_REQUEST:
        return duplicate_request(order)
    if decision.refund_amount == ZERO:
        return {
            "error": decision.code.value,
            "message": messages.RETURN_NOT_POSSIBLE,
            "order": order,
        }
    if amount != decision.refund_amount:
        return {
            "error": "AMOUNT_MISMATCH",
            "message": messages.AMOUNT_MISMATCH,
            "order": order,
            "refund_amount": str(decision.refund_amount),
            "refund_amount_text": format_money(
                str(decision.refund_amount), session.language
            ),
        }

    request_status = decision.request_status.value
    action = ReturnAction(order_id, reason, amount)
    if not session.approvals.consume(approval_token, action):
        session.approvals.request(action)
        return {
            "error": "APPROVAL_REQUIRED",
            "message": messages.APPROVAL_REQUIRED,
            "order": order,
            "reason": reason,
            "refund_amount": str(amount),
            "refund_amount_text": format_money(str(amount), session.language),
            "request_status": request_status,
        }

    # One statement checks for an existing request and inserts, so two
    # approved calls for the same order cannot both get through (R11).
    placeholders = ", ".join("?" for _ in BLOCKING_REQUEST_STATUSES)
    with conn:
        cursor = conn.execute(
            "INSERT INTO return_requests "
            "(order_id, customer_unique_id, reason, refund_amount, status, created_at) "
            "SELECT ?, ?, ?, ?, ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM return_requests "
            f"WHERE order_id = ? AND status IN ({placeholders}))",
            (
                order_id,
                session.customer_unique_id,
                reason,
                str(amount),
                request_status,
                f"{today.isoformat()} 00:00:00",
                order_id,
                *BLOCKING_REQUEST_STATUSES,
            ),
        )
    if cursor.rowcount == 0:
        return duplicate_request(order)

    return {
        "return_request_id": cursor.lastrowid,
        "message": messages.RETURN_REQUEST_CREATED,
        "order": order,
        "reason": reason,
        "refund_amount": str(amount),
        "refund_amount_text": format_money(str(amount), session.language),
        "status": request_status,
    }


def duplicate_request(order: str) -> dict:
    return {
        "error": "DUPLICATE_REQUEST",
        "message": messages.DUPLICATE_REQUEST,
        "order": order,
    }
