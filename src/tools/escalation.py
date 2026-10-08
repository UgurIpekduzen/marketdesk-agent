"""Handing a case over to a person.

Escalation changes no record: the case goes into an internal queue kept in
memory and one line is logged. The queue is lost when the process ends.

The summary is written by the model, so it is cleaned before it is kept:
raw ids are masked and the text is cut to a fixed length. The customer is
logged as a short hash, never as the id itself.
"""

import logging
from dataclasses import dataclass, field

from src import messages
from src.guardrails.pii import hash_id, mask_raw_ids
from src.tools.session import Session

logger = logging.getLogger(__name__)

PRIORITIES = ("low", "normal", "high")
MAX_SUMMARY_LENGTH = 500
TICKET_PREFIX = "ESC-"


@dataclass(frozen=True)
class Ticket:
    number: str
    priority: str
    summary: str
    customer_hash: str


@dataclass
class EscalationQueue:
    """Cases waiting for a person, oldest first."""

    tickets: list[Ticket] = field(default_factory=list)

    def add(self, priority: str, summary: str, customer_hash: str) -> Ticket:
        number = f"{TICKET_PREFIX}{len(self.tickets) + 1}"
        ticket = Ticket(number, priority, summary, customer_hash)
        self.tickets.append(ticket)
        return ticket


def escalate_to_human(
    session: Session,
    queue: EscalationQueue,
    summary: str,
    priority: str = "normal",
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
    summary = mask_raw_ids(summary.strip())[:MAX_SUMMARY_LENGTH]
    if not summary:
        return {"error": "EMPTY_SUMMARY", "message": messages.EMPTY_SUMMARY}

    ticket = queue.add(priority, summary, hash_id(session.customer_unique_id))
    logger.info(
        "escalation ticket=%s priority=%s customer=%s summary=%s",
        ticket.number,
        ticket.priority,
        ticket.customer_hash,
        ticket.summary,
    )
    return {
        "ticket": ticket.number,
        "priority": ticket.priority,
        "message": messages.ESCALATED,
    }
