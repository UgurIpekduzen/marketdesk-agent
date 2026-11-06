"""Pydantic AI in the framework comparison (eval/framework_compare.py).

Pydantic AI is not a dependency of the project: the task adds it for the run
only, so this module is imported only when the package is installed.
"""

import functools
import time

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from eval.framework_compare import lookup
from eval.framework_overhead import milliseconds_since


def scripted_response(
    state: dict, model_calls: int, messages, info: AgentInfo
) -> ModelResponse:
    """A tool call for every model call but the last, then the answer."""
    step = state["calls"]
    state["calls"] += 1
    if step < model_calls - 1:
        return ModelResponse(parts=[ToolCallPart("lookup", {"item": str(step)})])
    return ModelResponse(parts=[TextPart("done")])


def pydantic_agent(model_calls: int):
    """A Pydantic AI agent whose scripted model makes the given number of calls."""
    scripted = functools.partial(scripted_response, {"calls": 0}, model_calls)
    agent = Agent(FunctionModel(scripted), system_prompt="Answer briefly.")
    agent.tool_plain(lookup)
    return agent


async def pydantic_run(model_calls: int) -> tuple[float, float, int]:
    """One run of the Pydantic AI agent."""
    start = time.perf_counter()
    agent = pydantic_agent(model_calls)
    built = milliseconds_since(start)
    start = time.perf_counter()
    result = await agent.run("hello")
    return built, milliseconds_since(start), result.usage.requests
