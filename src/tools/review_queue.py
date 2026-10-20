"""The support rep's review queue: return requests and hand-over tickets.

No model takes part. The page shows the queue to a person in a support rep
session, and the person's click is the decision:

- a return request waiting for review (PENDING_REVIEW) can be approved or
  rejected, once; a request above the senior threshold (PENDING_SENIOR) is
  shown but cannot be decided here;
- an open ticket can be closed, once.

Each change is one UPDATE whose WHERE clause holds the state it starts from,
so a second click, or two reps at once, cannot decide a request twice. Only
a ReviewQueue made for the rep session can read or change anything, and the
page makes one only for that session.

Nothing here shows or logs a raw id: orders and customers are short hashes.
"""

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src import messages
from src.guardrails.pii import hash_id
from src.guardrails.write_access import restrict_writes
from src.rules.returns import RequestStatus
from src.tools.escalation import (
    TICKET_CLOSED,
    TICKET_OPEN,
    TICKETS_TABLE,
    ensure_tickets_table,
    ticket_number,
)

logger = logging.getLogger(__name__)

# The only identity that may hold a queue: the support rep session.
REP_IDENTITY = ("rep",)
DECISIONS = (RequestStatus.APPROVED, RequestStatus.REJECTED)
# The only values the console may change.
STATUS_COLUMNS = (("return_requests", "status"), (TICKETS_TABLE, "status"))
# How many decided requests the rep sees, newest first.
DECIDED_SHOWN = 20
PRIORITY_ORDER = "CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END"


class NotARepSession(PermissionError):
    """A queue was asked for outside the support rep session."""


@dataclass(frozen=True)
class RequestRow:
    request_id: int
    order_key: str  # hash of the order id
    customer_key: str  # hash of the customer, as on the tickets
    reason: str
    amount: str
    status: str
    created_at: str


@dataclass(frozen=True)
class TicketRow:
    ticket_id: int
    number: str
    customer_key: str
    priority: str
    summary: str  # written by the model: show it as plain text
    created_at: str


class ReviewQueue:
    def __init__(self, db_path: Path | str, identity: tuple) -> None:
        if tuple(identity) != REP_IDENTITY:
            raise NotARepSession(identity[0] if identity else None)
        self._db_path = db_path
        # A database built before tickets were kept gets the table, on a
        # connection of its own: the console's connections may not create it.
        conn = sqlite3.connect(db_path)
        try:
            with conn:
                ensure_tickets_table(conn)
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        # A short connection per call: the order servers write to the same
        # file, and nothing is held open between clicks. It may change the
        # status of a request or a ticket and nothing else.
        return restrict_writes(sqlite3.connect(self._db_path), updates=STATUS_COLUMNS)

    # --- Reading ------------------------------------------------------------

    def _requests(self, statuses: tuple[str, ...], order: str, limit: int | None):
        placeholders = ", ".join("?" for _ in statuses)
        query = (
            "SELECT id, order_id, customer_unique_id, reason, refund_amount, "
            "status, created_at FROM return_requests "
            f"WHERE status IN ({placeholders}) ORDER BY id {order}"
        )
        parameters: tuple = statuses
        if limit is not None:
            query += " LIMIT ?"
            parameters = (*statuses, limit)
        conn = self._connect()
        try:
            rows = conn.execute(query, parameters).fetchall()
        finally:
            conn.close()
        return [
            RequestRow(
                request_id=request_id,
                order_key=hash_id(order_id),
                customer_key=hash_id(customer),
                reason=reason,
                amount=str(amount),
                status=status,
                created_at=created_at,
            )
            for request_id, order_id, customer, reason, amount, status, created_at in rows
        ]

    def waiting_requests(self) -> list[RequestRow]:
        """Requests nobody has decided yet, oldest first."""
        return self._requests(
            (RequestStatus.PENDING_REVIEW, RequestStatus.PENDING_SENIOR), "ASC", None
        )

    def decided_requests(self) -> list[RequestRow]:
        """The latest decided requests, newest first."""
        return self._requests(DECISIONS, "DESC", DECIDED_SHOWN)

    def open_tickets(self) -> list[TicketRow]:
        """Open tickets, high priority first, then oldest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, customer_hash, priority, summary, created_at "
                f"FROM {TICKETS_TABLE} WHERE status = ? "
                f"ORDER BY {PRIORITY_ORDER}, id",
                (TICKET_OPEN,),
            ).fetchall()
        finally:
            conn.close()
        return [
            TicketRow(
                ticket_id, ticket_number(ticket_id), customer, priority, summary, at
            )
            for ticket_id, customer, priority, summary, at in rows
        ]

    # --- Deciding -----------------------------------------------------------

    def decide(self, request_id: int, decision: str) -> dict:
        """Approve or reject a request that waits for review."""
        if decision not in DECISIONS:
            return {
                "error": "INVALID_DECISION",
                "message": messages.REVIEW_INVALID_DECISION,
            }
        conn = self._connect()
        try:
            with conn:
                changed = conn.execute(
                    "UPDATE return_requests SET status = ? WHERE id = ? AND status = ?",
                    (decision, request_id, RequestStatus.PENDING_REVIEW),
                ).rowcount
            row = conn.execute(
                "SELECT order_id, status FROM return_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
        finally:
            conn.close()
        if changed:
            logger.info(
                "review decision request=%s order=%s status=%s",
                request_id,
                hash_id(row[0]),
                decision,
            )
            return {"request": request_id, "status": str(decision)}
        if row is None:
            return {"error": "NOT_FOUND", "message": messages.REVIEW_NOT_FOUND}
        if row[1] == RequestStatus.PENDING_SENIOR:
            return {"error": "SENIOR_ONLY", "message": messages.REVIEW_SENIOR_ONLY}
        return {"error": "ALREADY_DECIDED", "message": messages.REVIEW_ALREADY_DECIDED}

    def close_ticket(self, ticket_id: int) -> dict:
        """Close an open ticket."""
        conn = self._connect()
        try:
            with conn:
                changed = conn.execute(
                    f"UPDATE {TICKETS_TABLE} SET status = ? WHERE id = ? AND status = ?",
                    (TICKET_CLOSED, ticket_id, TICKET_OPEN),
                ).rowcount
            exists = conn.execute(
                f"SELECT 1 FROM {TICKETS_TABLE} WHERE id = ?", (ticket_id,)
            ).fetchone()
        finally:
            conn.close()
        if changed:
            logger.info("ticket closed ticket=%s", ticket_number(ticket_id))
            return {"ticket": ticket_number(ticket_id), "status": TICKET_CLOSED}
        if exists is None:
            return {"error": "NOT_FOUND", "message": messages.REVIEW_NOT_FOUND}
        return {
            "error": "ALREADY_CLOSED",
            "message": messages.REVIEW_TICKET_ALREADY_CLOSED,
        }
