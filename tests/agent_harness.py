"""Runs the Support Agent in a test: real MCP order server, stand-in model."""

import asyncio
import functools
import json
import sqlite3

from src.agents.support import SupportAgent
from src.i18n import DEFAULT_LANGUAGE
from src.mcp_server.client import OrdersClient
from src.orchestrator import Orchestrator
from tests.synthetic_data import ALICE


async def run_of_with_agent(db_path, customer, language, policy_index, fake, scenario):
    async with OrdersClient(db_path, customer, language) as orders:
        agent = await SupportAgent.create(
            orders, customer, policy_index, fake, language
        )
        return await scenario(agent)


def with_agent(
    db_path, policy_index, fake, scenario, customer=ALICE, language=DEFAULT_LANGUAGE
):
    """Start the order server and the agent, run the scenario, stop both.

    scenario is an async function that gets the agent. Everything runs in
    one task, as the MCP connection requires.
    """

    return asyncio.run(
        run_of_with_agent(db_path, customer, language, policy_index, fake, scenario)
    )


async def run_of_with_customer_router(
    db_path, customer, language, policy_index, fake, scenario
):
    async with OrdersClient(db_path, customer, language) as orders:
        router = await Orchestrator.for_customer(
            orders, customer, policy_index, fake, language
        )
        return await scenario(router)


def with_customer_router(
    db_path, policy_index, fake, scenario, customer=ALICE, language=DEFAULT_LANGUAGE
):
    """Like with_agent, but the scenario gets the router of a customer session."""

    return asyncio.run(
        run_of_with_customer_router(
            db_path, customer, language, policy_index, fake, scenario
        )
    )


async def scenario_of_asking(messages_to_send, agent):
    reply = None
    for message in messages_to_send:
        reply = await agent.ask(message)
    return reply


def asking(*messages_to_send):
    """A scenario that sends the messages in turn and returns the last reply."""

    return functools.partial(scenario_of_asking, messages_to_send)


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
