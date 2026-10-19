"""Chat with an agent from the command line.

Usage:  python -m src.cli --customer <customer_unique_id>
        python -m src.cli --demo
        python -m src.cli --ops

Who is signed in, and as what, is chosen when the program starts, the way a
login would, and never comes from what is typed into the chat. Every message
goes through the router: a customer session can reach the Support Agent, an
operations session (--ops) the Ops Data Agent, and nothing else. When the Support Agent asks to open a return request, the
request is shown and the person answers e (yes) or h (no); only then does
code write it.
"""

import argparse
import asyncio
import logging
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

from src import messages, tracing
from src.agents.ops import OpsAgent
from src.agents.support import SupportAgent
from src.formatting import how_computed
from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import PolicyIndex
from src.mcp_server.client import OrdersClient
from src.orchestrator import Orchestrator

DEFAULT_DB_PATH = Path("data/marketdesk.db")
# "çik" is what Python's lower() makes of "ÇIK" typed in capitals.
EXIT_WORDS = ("çık", "çik", "cik", "exit", "quit")
YES_WORDS = ("e", "evet")


async def chat(
    agent: Orchestrator | SupportAgent | OpsAgent,
    read: Callable[[str], str] = input,
    write: Callable[[str], None] = print,
    banner: str = messages.CHAT_BANNER,
) -> None:
    """Run the conversation until the person leaves."""
    write(banner)
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
        write(reply.display)
        # The router's answer wraps the agent's reply; an agent answers itself.
        for computation in getattr(getattr(reply, "reply", reply), "computations", []):
            write(f"{messages.COMPUTED_HEADING}: {how_computed(computation)}")

        # Only a customer session can have a return request waiting.
        if getattr(reply, "awaiting_approval", None) is not None:
            write(agent.approval_summary(reply.awaiting_approval))
            try:
                answer = read(messages.APPROVAL_QUESTION).strip().lower()
            except EOFError:
                # The input closed before an answer: that is no answer, so no.
                write(await agent.decline())
                break
            # Anything but a clear yes is a no.
            if answer in YES_WORDS:
                write(await agent.approve())
            else:
                write(await agent.decline())
    write(messages.CHAT_GOODBYE)


def demo_customer(conn: sqlite3.Connection) -> str:
    """The customer with the most orders: a convenient one to try things on."""
    return conn.execute(
        "SELECT customer_unique_id FROM customers GROUP BY customer_unique_id "
        "ORDER BY COUNT(*) DESC, customer_unique_id LIMIT 1"
    ).fetchone()[0]


async def run(db_path: Path, customer: str) -> None:
    """Start the order server for the customer and chat until they leave."""
    policy_index = PolicyIndex(load_embedder())
    async with OrdersClient(db_path, customer) as orders:
        router = await Orchestrator.for_customer(orders, customer, policy_index)
        await chat(router)


async def run_ops(db_path: Path) -> None:
    """Chat as operations staff until the person leaves."""
    router = Orchestrator.for_ops(db_path)
    try:
        await chat(router, banner=messages.CHAT_BANNER_OPS)
    finally:
        router.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--customer", help="customer_unique_id to sign in as")
    who.add_argument("--demo", action="store_true", help="sign in as a demo customer")
    who.add_argument("--ops", action="store_true", help="sign in as operations staff")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args(argv)

    # The step and token log of every run goes to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")

    # Does nothing unless a tracing target is set in config.py.
    tracing.setup_tracing()
    try:
        return sign_in_and_chat(args)
    finally:
        # Send the spans that are still waiting.
        tracing.shutdown_tracing()


def sign_in_and_chat(args: argparse.Namespace) -> int:
    if args.ops:
        asyncio.run(run_ops(args.db))
        return 0

    conn = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    try:
        customer = demo_customer(conn) if args.demo else args.customer
        owns_orders = conn.execute(
            "SELECT 1 FROM customers WHERE customer_unique_id = ? LIMIT 1", (customer,)
        ).fetchone()
    finally:
        conn.close()
    if owns_orders is None:
        print(messages.CHAT_UNKNOWN_CUSTOMER)
        return 1

    asyncio.run(run(args.db, customer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
