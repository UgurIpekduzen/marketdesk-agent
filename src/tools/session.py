"""The server-side session: who the customer is and which orders they saw.

Identity lives here and nowhere else. Tool functions read it from the
session; the model cannot pass or change it.

The session also gives every order a short alias (SIP-1, SIP-2, ...), so the
raw order id never has to appear in a tool's output. Aliases are numbered in
the order they are first handed out and mean nothing outside this session.

Approvals given by the person in this session are kept here as well, and
so are the values known to be personal for this customer (city, zip code
prefix), which the outbound guard keeps away from the model provider.
"""

import re
import sqlite3
from dataclasses import dataclass, field

from src.guardrails.approval import Approvals
from src.guardrails.outbound import Redactor
from src.i18n import DEFAULT_LANGUAGE, Language

CITY_MASK = "[city]"
ZIP_MASK = "[zip]"

ALIAS_PREFIX = "SIP-"
# Accepts "SIP-1", "sip-1", "SIP 1" and "sip1".
ALIAS_PATTERN = re.compile(r"SIP[- ]?(\d+)", re.IGNORECASE)


@dataclass
class Session:
    """The server-side session: the customer, the order aliases and the approvals."""

    customer_unique_id: str
    # Position n - 1 holds the order id behind the alias SIP-n.
    _order_ids: list[str] = field(default_factory=list, repr=False)
    approvals: Approvals = field(default_factory=Approvals, repr=False)
    # Personal value -> the mask that replaces it in text sent to the model.
    personal_values: dict[str, str] = field(default_factory=dict, repr=False)
    # The page's language, set when the session starts: how amounts are
    # written for the customer.
    language: Language = DEFAULT_LANGUAGE

    def alias_for(self, order_id: str) -> str:
        """Return the alias of an order, handing out a new one if needed.

        Args:
            order_id (str): An order id.

        Returns:
            Its alias.
        """
        if order_id not in self._order_ids:
            self._order_ids.append(order_id)
        return f"{ALIAS_PREFIX}{self._order_ids.index(order_id) + 1}"

    def order_id_for(self, order_ref: str) -> str:
        """Turn what the customer or the model wrote into an order id to look up.

        A known alias gives the order id behind it. Anything else is returned
        as it is, trimmed: it may be a raw order id typed by the customer.
        The result is only a candidate; whether the order belongs to this
        customer is decided by the query that uses it.

        Args:
            order_ref (str): An alias or an order number.

        Returns:
            The order id; the text itself when it is not an alias.
        """
        order_ref = order_ref.strip()
        match = ALIAS_PATTERN.fullmatch(order_ref)
        if match:
            number = int(match.group(1))
            if 1 <= number <= len(self._order_ids):
                return self._order_ids[number - 1]
        return order_ref

    def redactor(self) -> Redactor:
        """The cleaner for text that leaves this session for the model."""
        return Redactor(alias_for=self.alias_for, known_values=self.personal_values)


def open_session(
    conn: sqlite3.Connection,
    customer_unique_id: str,
    language: Language = DEFAULT_LANGUAGE,
) -> Session:
    """Start a session and load the customer's city and zip code prefix.

    A customer can have several of each, one per order. An unknown customer
    simply has none.

    Args:
        conn (sqlite3.Connection): A connection to the database.
        customer_unique_id (str): The customer.
        language (Language): The session's language.

    Returns:
        The session.
    """
    personal_values = {}
    rows = conn.execute(
        "SELECT DISTINCT customer_city, customer_zip_code_prefix "
        "FROM customers WHERE customer_unique_id = ?",
        (customer_unique_id,),
    )
    for city, zip_prefix in rows:
        if city:
            personal_values[city] = CITY_MASK
        if zip_prefix:
            personal_values[zip_prefix] = ZIP_MASK
    return Session(
        customer_unique_id, personal_values=personal_values, language=language
    )
