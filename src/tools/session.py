"""The server-side session: who the customer is and which orders they saw.

Identity lives here and nowhere else. Tool functions read it from the
session; the model cannot pass or change it.

The session also gives every order a short alias (SIP-1, SIP-2, ...), so the
raw order id never has to appear in a tool's output. Aliases are numbered in
the order they are first handed out and mean nothing outside this session.

Approvals given by the person in this session are kept here as well.
"""

import re
from dataclasses import dataclass, field

from src.guardrails.approval import Approvals

ALIAS_PREFIX = "SIP-"
# Accepts "SIP-1", "sip-1", "SIP 1" and "sip1".
ALIAS_PATTERN = re.compile(r"SIP[- ]?(\d+)", re.IGNORECASE)


@dataclass
class Session:
    customer_unique_id: str
    # Position n - 1 holds the order id behind the alias SIP-n.
    _order_ids: list[str] = field(default_factory=list, repr=False)
    approvals: Approvals = field(default_factory=Approvals, repr=False)

    def alias_for(self, order_id: str) -> str:
        """Return the alias of an order, handing out a new one if needed."""
        if order_id not in self._order_ids:
            self._order_ids.append(order_id)
        return f"{ALIAS_PREFIX}{self._order_ids.index(order_id) + 1}"

    def order_id_for(self, order_ref: str) -> str:
        """Turn what the customer or the model wrote into an order id to look up.

        A known alias gives the order id behind it. Anything else is returned
        as it is, trimmed: it may be a raw order id typed by the customer.
        The result is only a candidate; whether the order belongs to this
        customer is decided by the query that uses it.
        """
        order_ref = order_ref.strip()
        match = ALIAS_PATTERN.fullmatch(order_ref)
        if match:
            number = int(match.group(1))
            if 1 <= number <= len(self._order_ids):
                return self._order_ids[number - 1]
        return order_ref
