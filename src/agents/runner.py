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
from src import messages, tracing
from src.agents.run_log import RunLog

# Put on the trace when a run stops at the step limit.
STEP_LIMIT = "STEP_LIMIT"
# Put on the trace when the model asks for a tool the agent was not given.
UNKNOWN_TOOL = "UNKNOWN_TOOL"


async def run_agent(
    agent: FunctionAgent,
    context: Context,
    message: str,
    customer_unique_id: str | None = None,
) -> tuple[str, RunLog]:
    """Return the agent's answer to the message and what the run cost.

    Args:
        agent (FunctionAgent): The agent to run.
        context (Context): The conversation context.
        message (str): The person's message.
        customer_unique_id (str | None): The customer, for the log line; None when there
            is none.

    Returns:
        The agent's answer and the log of the run.
    """
    log = RunLog()
    given = {tool.metadata.name for tool in agent.tools}
    try:
        handler = agent.run(message, ctx=context, max_iterations=config.MAX_STEPS)
        async for event in handler.stream_events():
            if isinstance(event, AgentOutput):
                log.add_llm_call(event.raw)
            elif isinstance(event, ToolCallResult):
                log.add_tool_result(event.tool_name, str(event.tool_output.content))
            elif isinstance(event, ToolCall):
                log.add_tool_call(event.tool_name, event.tool_kwargs)
                if event.tool_name not in given:
                    log.unknown_tools.append(event.tool_name)
                    tracing.mark(error=UNKNOWN_TOOL, unknown_tool=event.tool_name)
        text = str(await handler).strip() or messages.EMPTY_REPLY
    except WorkflowRuntimeError as error:
        if "Max iterations" not in str(error):
            raise
        log.stopped_at_step_limit = True
        tracing.mark(error=STEP_LIMIT)
        text = messages.STEP_LIMIT_REACHED
    finally:
        log.write(agent.name, customer_unique_id)
    return text, log
