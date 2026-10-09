"""Runs one user message through an agent: the part every agent shares.

It counts model and tool calls into a RunLog, stops at the step limit with
a fixed message instead of a half-finished answer, and writes the log line
whatever happens.
"""

from llama_index.core.agent.workflow import (
    AgentOutput,
    FunctionAgent,
    ToolCall,
    ToolCallResult,
)
from llama_index.core.workflow import Context
from workflows.errors import WorkflowRuntimeError

import config
from src import messages
from src.agents.run_log import RunLog


async def run_agent(
    agent: FunctionAgent,
    context: Context,
    message: str,
    customer_unique_id: str | None = None,
) -> tuple[str, RunLog]:
    """Return the agent's answer to the message and what the run cost."""
    log = RunLog()
    try:
        handler = agent.run(message, ctx=context, max_iterations=config.MAX_STEPS)
        async for event in handler.stream_events():
            if isinstance(event, AgentOutput):
                log.add_llm_call(event.raw)
            elif isinstance(event, ToolCall) and not isinstance(event, ToolCallResult):
                log.add_tool_call(event.tool_name, event.tool_kwargs)
        text = str(await handler).strip() or messages.EMPTY_REPLY
    except WorkflowRuntimeError as error:
        if "Max iterations" not in str(error):
            raise
        log.stopped_at_step_limit = True
        text = messages.STEP_LIMIT_REACHED
    finally:
        log.write(agent.name, customer_unique_id)
    return text, log
