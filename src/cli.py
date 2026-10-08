"""Chat with the Support Agent from the command line.

Usage:  python -m src.cli --customer <customer_unique_id>
        python -m src.cli --demo

The customer is chosen when the program starts, the way a login would: it
never comes from what is typed into the chat. When the agent asks to open a
return request, the request is shown and the person answers e (yes) or h
(no); only then does code write it.
"""

import argparse
import asyncio
import logging
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

from src import messages
from src.agents.support import SupportAgent
from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import PolicyIndex
from src.tools.escalation import EscalationQueue
from src.tools.session import open_session

DEFAULT_DB_PATH = Path("data/marketdesk.db")
# "çik" is what Python's lower() makes of "ÇIK" typed in capitals.
EXIT_WORDS = ("çık", "çik", "cik", "exit", "quit")
YES_WORDS = ("e", "evet")


async def chat(
    agent: SupportAgent,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
) -> None:
    """Run the conversation until the person leaves."""
    write(messages.CHAT_BANNER)
    while True:
        try:
            line = read(messages.CHAT_PROMPT).strip()
        except EOFError:
            break
        if line.lower() in EXIT_WORDS:
            break
        if not line:
            continue

        reply = await agent.ask(line)
        write(reply.text)

        if reply.awaiting_approval is not None:
            write(agent.approval_summary())
            answer = read(messages.APPROVAL_QUESTION).strip().lower()
            # Anything but a clear yes is a no.
            write(agent.approve() if answer in YES_WORDS else agent.decline())
    write(messages.CHAT_GOODBYE)


def demo_customer(conn: sqlite3.Connection) -> str:
    """The customer with the most orders: a convenient one to try things on."""
    return conn.execute(
        "SELECT customer_unique_id FROM customers GROUP BY customer_unique_id "
        "ORDER BY COUNT(*) DESC, customer_unique_id LIMIT 1"
    ).fetchone()[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--customer", help="customer_unique_id to sign in as")
    who.add_argument("--demo", action="store_true", help="sign in as a demo customer")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args(argv)

    # The step and token log of every run goes to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    conn = sqlite3.connect(args.db)
    try:
        customer = demo_customer(conn) if args.demo else args.customer
        owns_orders = conn.execute(
            "SELECT 1 FROM customers WHERE customer_unique_id = ? LIMIT 1", (customer,)
        ).fetchone()
        if owns_orders is None:
            print(messages.CHAT_UNKNOWN_CUSTOMER)
            return 1
        agent = SupportAgent(
            open_session(conn, customer),
            conn,
            PolicyIndex(load_embedder()),
            EscalationQueue(),
        )
        asyncio.run(chat(agent))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
