"""A disk cache for model responses, so an evaluation can be run again
without using quota.

CachedLLM wraps the provider's model and sits inside the outbound guard, so
what it stores is the request as the provider would receive it. The key is
a hash of everything that decides the answer: provider and model name,
temperature, the messages and the tools offered. Change the system prompt,
a tool description or the model, and the key changes with it.

With each response the cache keeps the token counts and the time the real
call took, so a run answered from the cache reports the same cost as the
run that filled it.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, LLMMetadata
from llama_index.core.llms.function_calling import FunctionCallingLLM
from pydantic import ConfigDict, Field

import config
from src.agents.run_log import token_usage

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"
# Marks, lower case, of an error that passes by itself: the provider is
# overloaded or the rate limit of the minute is used up.
TRANSIENT_MARKS = ("503", "unavailable", "overloaded", "429", "resource_exhausted")


# Marks of the error that says the free quota of the day is used up: it
# comes as a 429 like the one of the minute, but waiting does not help.
DAILY_QUOTA_MARKS = ("perday", "per_day", "per day")


# Marks of the error that says the paid key's prepaid credit is gone (402):
# it also says RESOURCE_EXHAUSTED, but waiting does not help.
NO_CREDIT_MARKS = ("prepayment credits", "402 resource_exhausted")


class DailyQuotaUsedUpError(RuntimeError):
    """The free daily quota is gone: the run stops, to go on with --paid."""


class NoPaidCreditError(RuntimeError):
    """The paid key has no prepaid credit left: the run stops until some is added."""


class LiveCallLimitReachedError(RuntimeError):
    """A run made as many live calls as it may (config.PAID_RUN_MAX_LIVE_CALLS)."""


def error_text(failure: BaseException) -> str:
    """The error's type and message, lower case, for matching."""
    return f"{type(failure).__name__} {failure}".lower()


def is_transient(failure: BaseException) -> bool:
    """Whether an error of the provider is worth waiting out."""
    text = error_text(failure)
    return (
        any(mark in text for mark in TRANSIENT_MARKS)
        and not is_daily_quota(failure)
        and not is_out_of_credit(failure)
    )


def is_daily_quota(failure: BaseException) -> bool:
    """Whether the error says the quota of the day, not of the minute, is gone."""
    text = error_text(failure)
    return ("429" in text or "resource_exhausted" in text) and any(
        mark in text for mark in DAILY_QUOTA_MARKS
    )


def is_out_of_credit(failure: BaseException) -> bool:
    """Whether the error says the paid key's prepaid credit is used up."""
    text = error_text(failure)
    return any(mark in text for mark in NO_CREDIT_MARKS)


def daily_quota_message(provider_class: str) -> str:
    """What to do once a provider's daily limit stopped a run."""
    if provider_class == "GoogleGenAI":
        return (
            "The free daily quota is used up. Run the same command again with "
            "--paid to finish on the paid key; the answers so far are in the cache."
        )
    return (
        f"The daily limit of {provider_class} is used up. Run the same command "
        "again tomorrow; the answers so far are in the cache."
    )


async def one_piece(response):
    """A stream that holds one whole response."""
    yield response


class CachedLLM(FunctionCallingLLM):
    """A model that answers from the cache and calls the wrapped model on a miss."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: FunctionCallingLLM = Field(exclude=True)
    cache_dir: Path = DEFAULT_CACHE_DIR
    # What this cache was used for since it was created.
    hits: int = 0
    live_calls: int = 0
    seconds: float = 0.0
    # A busy provider is asked again this many times, this far apart.
    retries: int = 4
    retry_seconds: float = 30.0
    # Live calls this cache may make; None for no limit. Set for a run on
    # the paid key, so that nothing can run up the bill.
    max_live_calls: int | None = None
    # Decides from the text of an answer whether it is kept for next time.
    # An answer it refuses is returned but not stored, so asking again asks the
    # provider again (a refusal kept would be the answer for ever).
    keep: Callable[[str], bool] | None = Field(default=None, exclude=True)

    @classmethod
    def class_name(cls) -> str:
        """Name used by LlamaIndex for this model class."""
        return "CachedLLM"

    @property
    def metadata(self) -> LLMMetadata:
        """Metadata of the wrapped model."""
        return self.inner.metadata

    def _key(self, messages: Sequence[ChatMessage], kwargs: dict) -> str:
        request = {
            "provider": type(self.inner).__name__,
            "model": self.inner.metadata.model_name,
            "temperature": config.LLM_TEMPERATURE,
            "messages": [message.model_dump(mode="json") for message in messages],
            "kwargs": kwargs,
        }
        # Settings the model was built with, such as how much a reasoning
        # model thinks, change its answer. Only added when there are some,
        # so the keys of every model built without them stay as they were.
        settings = getattr(self.inner, "additional_kwargs", None)
        if settings:
            request["settings"] = settings
        encoded = json.dumps(request, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(encoded.encode()).hexdigest()

    def _load(self, key: str) -> dict | None:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _store(self, key: str, entry: dict) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    def _from_entry(self, entry: dict) -> ChatResponse:
        self.seconds += entry["seconds"]
        return ChatResponse(
            message=ChatMessage.model_validate(entry["message"]),
            raw={
                "usage_metadata": {
                    "prompt_token_count": entry["input_tokens"],
                    "candidates_token_count": entry["output_tokens"],
                }
            },
        )

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        """Answer from the cache, or call the wrapped model and store the answer."""
        key = self._key(messages, kwargs)
        entry = self._load(key)
        if entry is None:
            response, started = await self._call_with_retries(messages, kwargs)
            input_tokens, output_tokens = token_usage(response.raw)
            entry = {
                "message": response.message.model_dump(mode="json"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "seconds": round(time.perf_counter() - started, 3),
            }
            if self.keep is None or self.keep(response.message.content or ""):
                self._store(key, entry)
            self.live_calls += 1
        else:
            self.hits += 1
        return self._from_entry(entry)

    async def _call_with_retries(
        self, messages: Sequence[ChatMessage], kwargs: dict
    ) -> tuple[ChatResponse, float]:
        """Call the provider; wait and try again when it is only busy.

        Returns the response and when the attempt that got it started, so
        the waiting is not counted as the model's time.
        """
        if self.max_live_calls is not None and self.live_calls >= self.max_live_calls:
            raise LiveCallLimitReachedError(
                f"{self.live_calls} live calls made, the limit of this run"
            )
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            try:
                return await self.inner.achat(messages, **kwargs), started
            except Exception as failure:
                if is_daily_quota(failure):
                    raise DailyQuotaUsedUpError(
                        daily_quota_message(type(self.inner).__name__)
                    ) from failure
                if is_out_of_credit(failure):
                    raise NoPaidCreditError(
                        "The paid key has no prepaid credit left. Add credit in "
                        "AI Studio (the project's Billing page) and run the same "
                        "command again; the answers so far are in the cache."
                    ) from failure
                if attempt == self.retries or not is_transient(failure):
                    raise
                logger.warning(
                    "provider is busy (attempt %d of %d), waiting %.0f s",
                    attempt + 1,
                    self.retries + 1,
                    self.retry_seconds,
                )
                await asyncio.sleep(self.retry_seconds)
        raise AssertionError("unreachable")

    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        """Stream the cached or fresh answer as one piece."""
        # One whole response instead of pieces: a cached answer has no pieces.
        response = await self.achat(messages, **kwargs)
        return one_piece(response)

    # --- Not used by the agents; refused so nothing goes round the cache ---

    def _not_cached(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("CachedLLM supports achat and astream_chat only")

    chat = stream_chat = complete = stream_complete = _not_cached
    acomplete = astream_complete = _not_cached

    # --- Tool calling: provider-specific parts, left to the real model ----

    def _prepare_chat_with_tools(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.inner._prepare_chat_with_tools(*args, **kwargs)

    def _validate_chat_with_tools_response(
        self, *args: Any, **kwargs: Any
    ) -> ChatResponse:
        return self.inner._validate_chat_with_tools_response(*args, **kwargs)

    def get_tool_calls_from_response(self, *args: Any, **kwargs: Any) -> list:
        """Read the tool calls from a response, as the wrapped model does."""
        return self.inner.get_tool_calls_from_response(*args, **kwargs)
