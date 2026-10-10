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

import hashlib
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, LLMMetadata
from llama_index.core.llms.function_calling import FunctionCallingLLM
from pydantic import ConfigDict, Field

import config
from src.agents.run_log import token_usage

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache"


class CachedLLM(FunctionCallingLLM):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    inner: FunctionCallingLLM = Field(exclude=True)
    cache_dir: Path = DEFAULT_CACHE_DIR
    # What this cache was used for since it was created.
    hits: int = 0
    live_calls: int = 0
    seconds: float = 0.0

    @classmethod
    def class_name(cls) -> str:
        return "CachedLLM"

    @property
    def metadata(self) -> LLMMetadata:
        return self.inner.metadata

    def _key(self, messages: Sequence[ChatMessage], kwargs: dict) -> str:
        request = {
            "provider": type(self.inner).__name__,
            "model": self.inner.metadata.model_name,
            "temperature": config.LLM_TEMPERATURE,
            "messages": [message.model_dump(mode="json") for message in messages],
            "kwargs": kwargs,
        }
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
        key = self._key(messages, kwargs)
        entry = self._load(key)
        if entry is None:
            started = time.perf_counter()
            response = await self.inner.achat(messages, **kwargs)
            input_tokens, output_tokens = token_usage(response.raw)
            entry = {
                "message": response.message.model_dump(mode="json"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "seconds": round(time.perf_counter() - started, 3),
            }
            self._store(key, entry)
            self.live_calls += 1
        else:
            self.hits += 1
        return self._from_entry(entry)

    async def astream_chat(self, messages: Sequence[ChatMessage], **kwargs: Any):
        # One whole response instead of pieces: a cached answer has no pieces.
        response = await self.achat(messages, **kwargs)

        async def stream():
            yield response

        return stream()

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
        return self.inner.get_tool_calls_from_response(*args, **kwargs)
