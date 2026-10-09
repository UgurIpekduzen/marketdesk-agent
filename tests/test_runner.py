"""Tests for the run loop every agent shares, with a stand-in model."""

import asyncio
import logging

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

import config
from src import messages
from src.agents.runner import run_agent
from tests.fakes import FakeLLM


async def echo(text: str) -> str:
    """Return the text."""
    return text


def run(script, message="merhaba", customer=None):
    async def scenario():
        agent = FunctionAgent(
            name="trial",
            tools=[FunctionTool.from_defaults(async_fn=echo)],
            llm=FakeLLM(script=script),
            system_prompt="system",
        )
        return await run_agent(agent, Context(agent), message, customer)

    return asyncio.run(scenario())


def test_answer_and_counts():
    text, log = run([[("echo", {"text": "a"})], "bitti"])

    assert text == "bitti"
    assert (log.llm_calls, log.tool_calls) == (2, ["echo"])
    assert log.tool_arguments == [{"text": "a"}]
    assert log.stopped_at_step_limit is False


def test_step_limit_gives_the_fixed_message():
    text, log = run([[("echo", {"text": str(n)})] for n in range(30)])

    assert text == messages.STEP_LIMIT_REACHED
    assert log.stopped_at_step_limit is True
    assert log.llm_calls == config.MAX_STEPS


def test_empty_answer_gives_the_fixed_message():
    text, _ = run(["  "])

    assert text == messages.EMPTY_REPLY


def test_run_is_logged_under_the_agents_name(caplog):
    with caplog.at_level(logging.INFO, logger="src.agents.run_log"):
        run(["tamam"])

    line = caplog.records[0].getMessage()
    assert "agent=trial" in line
    assert "customer=-" in line
