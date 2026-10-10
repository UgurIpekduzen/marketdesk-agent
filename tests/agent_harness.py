"""Runs the Support Agent in a test: real MCP order server, stand-in model."""

import asyncio
import json
import sqlite3

from src.agents.support import SupportAgent
from src.mcp_server.client import OrdersClient
from src.orchestrator import Orchestrator
from src.tools.escalation import EscalationQueue
from tests.synthetic_data import ALICE


def with_agent(db_path, policy_index, fake, scenario, customer=ALICE, queue=None):
    """Start the order server and the agent, run the scenario, stop both.

    scenario is an async function that gets the agent. Everything runs in
    one task, as the MCP connection requires.
    """

    async def run():
        async with OrdersClient(db_path, customer) as orders:
            agent = await SupportAgent.create(
                orders, customer, policy_index, queue or EscalationQueue(), fake
            )
            return await scenario(agent)

    return asyncio.run(run())


def with_customer_router(db_path, policy_index, fake, scenario, customer=ALICE):
    """Like with_agent, but the scenario gets the router of a customer session."""

    async def run():
        async with OrdersClient(db_path, customer) as orders:
            router = await Orchestrator.for_customer(
                orders, customer, policy_index, EscalationQueue(), fake
            )
            return await scenario(router)

    return asyncio.run(run())


def asking(*messages_to_send):
    """A scenario that sends the messages in turn and returns the last reply."""

    async def scenario(agent):
        reply = None
        for message in messages_to_send:
            reply = await agent.ask(message)
        return reply

    return scenario


def tool_results(fake):
    """The tool results in the last request the model received, parsed."""
    return [
        json.loads(block["text"])
        for message in fake.requests[-1]["messages"]
        if message["role"] == "tool"
        for block in message["blocks"]
    ]


def request_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]
    finally:
        conn.close()
