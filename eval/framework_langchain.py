"""LangChain on LangGraph in the framework comparison (eval/framework_compare.py).

LangChain is not a dependency of the project: the task adds it for the run
only, so this module is imported only when the package is installed.
"""

import time

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from pydantic import Field

from eval.framework_compare import lookup
from eval.framework_overhead import milliseconds_since


class ScriptedChatModel(BaseChatModel):
    """A LangChain chat model that plays a script: a tool call, then the answer."""

    model_calls: int
    made: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        """Return the model itself: the script decides the calls."""
        return self

    def _next(self) -> ChatResult:
        step = len(self.made)
        self.made.append(step)
        if step < self.model_calls - 1:
            call = {"name": "lookup", "args": {"item": str(step)}, "id": f"c{step}"}
            message = AIMessage(content="", tool_calls=[call])
        else:
            message = AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._next()

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._next()


def langchain_agent(model_calls: int):
    """A LangChain agent whose scripted model makes the given number of calls."""
    model = ScriptedChatModel(model_calls=model_calls, made=[])
    agent = create_agent(model, tools=[tool(lookup)], system_prompt="Answer briefly.")
    return agent, model


async def langchain_run(model_calls: int) -> tuple[float, float, int]:
    """One run of the LangChain agent."""
    start = time.perf_counter()
    agent, model = langchain_agent(model_calls)
    built = milliseconds_since(start)
    start = time.perf_counter()
    await agent.ainvoke({"messages": [("user", "hello")]})
    return built, milliseconds_since(start), len(model.made)
