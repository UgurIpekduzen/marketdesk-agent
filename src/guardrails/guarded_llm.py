"""The one way to the model provider.

Every agent gets its model from build_llm. What it gets is a GuardedLLM: a
wrapper that looks like a model to the agent, cleans every outgoing message
with the session's Redactor, and only then calls the real model. No other
module creates or imports a provider's model class.

What is cleaned: the text of every message in the request (system prompt,
user messages, the model's own earlier turns, tool results) and the
arguments of earlier tool calls. What comes back from the model is passed
on unchanged: the model can only repeat what it was sent.
"""

import os
from collections import Counter
from collections.abc import AsyncGenerator, Generator, Sequence
from typing import Any

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMMetadata,
)
from llama_index.core.llms.function_calling import FunctionCallingLLM
from pydantic import ConfigDict, Field

import config
from src import tracing
from src.guardrails.outbound import Redactor, findings_summary, log_findings

API_KEY_VARIABLES = {"gemini": "GEMINI_API_KEY_FREE", "groq": "GROQ_API_KEY"}


class GuardedLLM(FunctionCallingLLM):
    """A model that cleans every request before passing it on."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: FunctionCallingLLM = Field(exclude=True)
    redactor: Redactor = Field(exclude=True)

    @classmethod
    def class_name(cls) -> str:
        return "GuardedLLM"

    @property
    def metadata(self) -> LLMMetadata:
        return self.inner.metadata

    # --- Cleaning --------------------------------------------------------

    def _clean_text(self, text: str) -> str:
        cleaned, found = self.redactor.redact(text)
        self._report(found)
        return cleaned

    def _clean_messages(self, messages: Sequence[ChatMessage]) -> list[ChatMessage]:
        """Clean every string in every message, whatever field it is in."""
        found: Counter = Counter()
        cleaned = [
            ChatMessage.model_validate(
                self.redactor.redact_value(message.model_dump(), found)
            )
            for message in messages
        ]
        self._report(found)
        return cleaned

    @staticmethod
    def _report(found: Counter) -> None:
        """Log what was replaced and put it on the trace: kinds and counts."""
        log_findings(found)
        if found:
            tracing.mark(masked=findings_summary(found))

    # --- Chat: the calls an agent makes ----------------------------------

    def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        return self.inner.chat(self._clean_messages(messages), **kwargs)

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        return await self.inner.achat(self._clean_messages(messages), **kwargs)

    def stream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> Generator[ChatResponse, None, None]:
        return self.inner.stream_chat(self._clean_messages(messages), **kwargs)

    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> AsyncGenerator[ChatResponse, None]:
        return await self.inner.astream_chat(self._clean_messages(messages), **kwargs)

    # --- Plain completion ------------------------------------------------

    def complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        return self.inner.complete(self._clean_text(prompt), formatted, **kwargs)

    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        return await self.inner.acomplete(self._clean_text(prompt), formatted, **kwargs)

    def stream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> Generator[CompletionResponse, None, None]:
        return self.inner.stream_complete(self._clean_text(prompt), formatted, **kwargs)

    async def astream_complete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> AsyncGenerator[CompletionResponse, None]:
        return await self.inner.astream_complete(
            self._clean_text(prompt), formatted, **kwargs
        )

    # --- Tool calling: provider-specific parts, left to the real model ---
    #
    # The base class turns a tool-calling request into a call to chat,
    # achat, stream_chat or astream_chat above, so it is cleaned there.

    def _prepare_chat_with_tools(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.inner._prepare_chat_with_tools(*args, **kwargs)

    def _validate_chat_with_tools_response(
        self, *args: Any, **kwargs: Any
    ) -> ChatResponse:
        return self.inner._validate_chat_with_tools_response(*args, **kwargs)

    def get_tool_calls_from_response(self, *args: Any, **kwargs: Any) -> list:
        return self.inner.get_tool_calls_from_response(*args, **kwargs)


def configured_model() -> tuple[str, str]:
    """(provider, model name) to use now: the main one, or the fallback."""
    if config.LLM_USE_FALLBACK:
        return config.LLM_FALLBACK_PROVIDER, config.LLM_FALLBACK_MODEL
    return config.LLM_PROVIDER, config.LLM_MODEL


def build_provider_llm(
    provider: str | None = None,
    model: str | None = None,
    paid: bool = False,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> FunctionCallingLLM:
    """Create a provider's model: by default the one config.py names.

    paid uses the key of the project with billing (config.PAID_KEY_VARIABLE)
    instead of the free one; only evaluation runs started with --paid pass
    it, never the page or the agents. reasoning_effort sets how much a
    reasoning model on Groq thinks before it answers. temperature, when
    given, replaces config.LLM_TEMPERATURE. max_tokens, when given, limits
    the length of an answer; without it the provider decides.
    """
    if provider is None or model is None:
        provider, model = configured_model()
    if provider not in API_KEY_VARIABLES:
        raise ValueError(f"unknown LLM provider in config.py: {provider!r}")
    if paid and provider != "gemini":
        raise ValueError("the paid key is a Gemini key")
    if reasoning_effort is not None and provider != "groq":
        raise ValueError("reasoning_effort is a setting of Groq's reasoning models")
    api_key = os.environ[
        config.PAID_KEY_VARIABLE if paid else API_KEY_VARIABLES[provider]
    ]
    if temperature is None:
        temperature = config.LLM_TEMPERATURE

    # Only named when asked, so a model built without a limit is as it was.
    length = {} if max_tokens is None else {"max_tokens": max_tokens}

    # Imported here: this is the only place that knows the providers.
    if provider == "gemini":
        from llama_index.llms.google_genai import GoogleGenAI

        return GoogleGenAI(
            model=model, api_key=api_key, temperature=temperature, **length
        )
    from llama_index.llms.groq import Groq

    return Groq(
        model=model,
        api_key=api_key,
        temperature=temperature,
        **length,
        additional_kwargs=(
            {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
        ),
    )


def build_judge_provider_llm(paid: bool = False) -> FunctionCallingLLM:
    """The provider's model that scores answers in the evaluation."""
    return build_provider_llm(config.JUDGE_PROVIDER, config.JUDGE_MODEL, paid)


def build_llm(redactor: Redactor | None = None) -> GuardedLLM:
    """The model for an agent: the provider's model behind the guard.

    Pass the session's redactor in a customer session; without one, ids are
    masked instead of being replaced by aliases.
    """
    return GuardedLLM(inner=build_provider_llm(), redactor=redactor or Redactor())
