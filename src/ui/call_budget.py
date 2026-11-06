"""How many model calls all visitors together may make in one day.

The hourly question limit counts questions, but one question may take
several calls: the router's and one for every step of the agent. The free
tier's quota counts calls, so this budget does too. Like the question limit
it is shared by the whole server process, and it is counted at each call,
so a run that would go past it stops in the middle.
"""

import threading
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable, Generator, Sequence
from typing import Any

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMMetadata,
)
from llama_index.core.llms.function_calling import FunctionCallingLLM
from pydantic import ConfigDict, Field, SkipValidation

from src.failures import BUDGET_MARK

WINDOW_SECONDS = 24 * 3600


class CallBudgetReachedError(RuntimeError):
    """The model calls of the last day have used up the budget."""


class CallBudget:
    """The model calls the page may make per day, for the whole process."""

    def __init__(
        self,
        per_day: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._per_day = per_day
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def _forget_old(self, now: float) -> None:
        while self._calls and now - self._calls[0] >= WINDOW_SECONDS:
            self._calls.popleft()

    def check(self) -> None:
        """Refuse when nothing is left, without counting a call."""
        with self._lock:
            self._forget_old(self._clock())
            if len(self._calls) >= self._per_day:
                raise CallBudgetReachedError(
                    f"{BUDGET_MARK} of {self._per_day} used up"
                )

    def take(self) -> None:
        """Count one model call, or refuse it when the day is full."""
        with self._lock:
            now = self._clock()
            self._forget_old(now)
            if len(self._calls) >= self._per_day:
                raise CallBudgetReachedError(
                    f"{BUDGET_MARK} of {self._per_day} used up"
                )
            self._calls.append(now)


class CountedLLM(FunctionCallingLLM):
    """A model that takes one call from the budget before every request."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: FunctionCallingLLM = Field(exclude=True)
    # Not checked at run time: the page keeps one budget for the whole process,
    # and a module loaded a second time has a new CallBudget class that would
    # refuse the old budget. The model only calls take().
    budget: SkipValidation[CallBudget] = Field(exclude=True)

    @classmethod
    def class_name(cls) -> str:
        """Name used by LlamaIndex for this model class."""
        return "CountedLLM"

    @property
    def metadata(self) -> LLMMetadata:
        """Metadata of the wrapped model."""
        return self.inner.metadata

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        """Take one call from the budget, then chat.

        Args:
            messages (Sequence[ChatMessage]): The messages to send.
            **kwargs: Passed on to the wrapped model.

        Returns:
            The wrapped model's response.
        """
        self.budget.take()
        return self.inner.chat(messages, **kwargs)

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        """Take one call from the budget, then chat (async).

        Args:
            messages (Sequence[ChatMessage]): The messages to send.
            **kwargs: Passed on to the wrapped model.

        Returns:
            The wrapped model's response.
        """
        self.budget.take()
        return await self.inner.achat(messages, **kwargs)

    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> Generator[ChatResponse, None, None]:
        """Take one call from the budget, then stream a chat reply.

        Args:
            messages (Sequence[ChatMessage]): The messages to send.
            **kwargs: Passed on to the wrapped model.

        Returns:
            A generator of response pieces.
        """
        self.budget.take()
        return self.inner.stream_chat(messages, **kwargs)

    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> AsyncGenerator[ChatResponse, None]:
        """Take one call from the budget, then stream a chat reply (async).

        Args:
            messages (Sequence[ChatMessage]): The messages to send.
            **kwargs: Passed on to the wrapped model.

        Returns:
            An async generator of response pieces.
        """
        self.budget.take()
        return await self.inner.astream_chat(messages, **kwargs)

    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        """Take one call from the budget, then complete the prompt.

        Args:
            prompt (str): The prompt to complete.
            formatted (bool): True when the prompt already has the model's format.
            **kwargs: Passed on to the wrapped model.

        Returns:
            The wrapped model's response.
        """
        self.budget.take()
        return self.inner.complete(prompt, formatted, **kwargs)

    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        """Take one call from the budget, then complete the prompt (async).

        Args:
            prompt (str): The prompt to complete.
            formatted (bool): True when the prompt already has the model's format.
            **kwargs: Passed on to the wrapped model.

        Returns:
            The wrapped model's response.
        """
        self.budget.take()
        return await self.inner.acomplete(prompt, formatted, **kwargs)

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> Generator[CompletionResponse, None, None]:
        """Take one call from the budget, then stream the completion.

        Args:
            prompt (str): The prompt to complete.
            formatted (bool): True when the prompt already has the model's format.
            **kwargs: Passed on to the wrapped model.

        Returns:
            A generator of response pieces.
        """
        self.budget.take()
        return self.inner.stream_complete(prompt, formatted, **kwargs)

    async def astream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> AsyncGenerator[CompletionResponse, None]:
        """Take one call from the budget, then stream the completion (async).

        Args:
            prompt (str): The prompt to complete.
            formatted (bool): True when the prompt already has the model's format.
            **kwargs: Passed on to the wrapped model.

        Returns:
            An async generator of response pieces.
        """
        self.budget.take()
        return await self.inner.astream_complete(prompt, formatted, **kwargs)

    # Tool calling: the base class turns it into one of the calls above.

    def _prepare_chat_with_tools(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.inner._prepare_chat_with_tools(*args, **kwargs)

    def _validate_chat_with_tools_response(
        self, *args: Any, **kwargs: Any
    ) -> ChatResponse:
        return self.inner._validate_chat_with_tools_response(*args, **kwargs)

    def get_tool_calls_from_response(self, *args: Any, **kwargs: Any) -> list:
        """Read the tool calls from a response, as the wrapped model does.

        Args:
            *args: Passed on to the wrapped model.
            **kwargs: Passed on to the wrapped model.

        Returns:
            The tool calls in the response.
        """
        return self.inner.get_tool_calls_from_response(*args, **kwargs)
