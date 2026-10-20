"""Handing a case over to a person.

Escalation changes no order and no return request: the case becomes one row
of the escalation_tickets table, the queue a support rep works through, and
one line is logged. The order server is the only caller, so the tickets are
written where the return requests are.

The summary is written by the model, so it is cleaned before it is kept,
logged and shown to the rep: it passes the same guard as text sent to the
model provider (raw ids, e-mail addresses, phone and id numbers, the
session's city and zip code) and is cut to a fixed length. The customer is
kept and logged as a short hash, never as the id itself.
"""

import logging
import sqlite3
from datetime import date

import config
from src import messages
from src.guardrails.outbound import Redactor
from src.guardrails.pii import hash_id
from src.tools.session import Session

logger = logging.getLogger(__name__)

PRIORITIES = ("low", "normal", "high")
MAX_SUMMARY_LENGTH = 500
TICKET_PREFIX = "ESC-"

TICKETS_TABLE = "escalation_tickets"
TICKET_OPEN = "OPEN"
TICKET_CLOSED = "CLOSED"
# IF NOT EXISTS: a database built before tickets were kept gets the table
# when it is next opened.
TICKETS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TICKETS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_hash TEXT NOT NULL,
    priority TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def clean_summary(summary: str, session: Session) -> str:
    """A summary as it may be kept, logged and shown: personal data masked
    (raw ids as [id], not as the session's aliases) and cut."""
    redactor = Redactor(known_values=session.personal_values)
    return redactor.redact(summary.strip())[0][:MAX_SUMMARY_LENGTH]


def ensure_tickets_table(conn: sqlite3.Connection) -> None:
    """Create the tickets table unless the database has it."""
    with conn:
        conn.execute(TICKETS_TABLE_SQL)


def ticket_number(ticket_id: int) -> str:
    """The number a person reads: ESC-12."""
    return f"{TICKET_PREFIX}{ticket_id}"


def escalate_to_human(
    session: Session,
    conn: sqlite3.Connection,
    summary: str,
    priority: str = "normal",
    today: date = config.SIMULATED_TODAY,
) -> dict:
    """Hand the current customer's case over to a human agent.

    Use it when the rules answer NEEDS_HUMAN, when the policy does not cover
    the question, or when the customer asks for a person. summary says in
    one or two sentences what the customer needs; refer to orders by their
    alias (for example SIP-1) and leave out names, addresses and order
    numbers. priority is low, normal or high.

    Nothing about the order is changed. The result holds the ticket number
    to give to the customer.
    """
    if priority not in PRIORITIES:
        return {
            "error": "INVALID_PRIORITY",
            "message": messages.INVALID_PRIORITY.format(allowed=", ".join(PRIORITIES)),
        }
    summary = clean_summary(summary, session)
    if not summary:
        return {"error": "EMPTY_SUMMARY", "message": messages.EMPTY_SUMMARY}

    customer_hash = hash_id(session.customer_unique_id)
    with conn:
        cursor = conn.execute(
            f"INSERT INTO {TICKETS_TABLE} "
            "(customer_hash, priority, summary, status, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                customer_hash,
                priority,
                summary,
                TICKET_OPEN,
                f"{today.isoformat()} 00:00:00",
            ),
        )
    number = ticket_number(cursor.lastrowid)
    logger.info(
        "escalation ticket=%s priority=%s customer=%s summary=%s",
        number,
        priority,
        customer_hash,
        summary,
    )
    return {
        "ticket": number,
        "priority": priority,
        "message": messages.ESCALATED,
    }
