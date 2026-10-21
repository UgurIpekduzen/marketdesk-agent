"""A stand-in for the model provider: no network, no API key.

FakeLLM plays back a script and records every request it receives, exactly
as a provider would see it. A script step is either a text (the model's
answer), a list of (tool name, arguments) pairs (the model asks for
tools) or an exception (the provider fails).
"""

from collections.abc import Sequence
from typing import Any

from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMMetadata,
    MessageRole,
    TextBlock,
    ToolCallBlock,
)
from llama_index.core.llms.function_calling import FunctionCallingLLM
from llama_index.core.tools import ToolSelection
from pydantic import Field


class FakeLLM(FunctionCallingLLM):
    script: list = Field(default_factory=list)
    # Every request, as the provider would receive it.
    requests: list = Field(default_factory=list)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            model_name="fake", is_chat_model=True, is_function_calling_model=True
        )

    def sent_text(self) -> str:
        """Everything sent to the provider so far, as one text."""
        return "\n".join(str(request) for request in self.requests)

    def _answer(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResponse:
        self.requests.append(
            {
                "messages": [message.model_dump() for message in messages],
                "kwargs": {key: str(value) for key, value in kwargs.items()},
                # Names of the tools this request offered to the model.
                "tools": [tool["function"]["name"] for tool in kwargs.get("tools", [])],
            }
        )
        step = self.script.pop(0) if self.script else "(end of script)"
        # An exception in the script is raised, as a failing provider would.
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, str):
            blocks = [TextBlock(text=step)]
        else:
            blocks = [
                ToolCallBlock(
                    tool_call_id=f"call-{len(self.requests)}-{number}",
                    tool_name=name,
                    tool_kwargs=arguments,
                )
                for number, (name, arguments) in enumerate(step)
            ]
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, blocks=blocks)
        )

    def chat(self, messages, **kwargs):
        return self._answer(messages, **kwargs)

    async def achat(self, messages, **kwargs):
        return self._answer(messages, **kwargs)

    def stream_chat(self, messages, **kwargs):
        yield self._answer(messages, **kwargs)

    async def astream_chat(self, messages, **kwargs):
        response = self._answer(messages, **kwargs)

        async def stream():
            yield response

        return stream()

    def complete(self, prompt, formatted=False, **kwargs):
        self.requests.append({"prompt": prompt})
        return CompletionResponse(text="(completion)")

    async def acomplete(self, prompt, formatted=False, **kwargs):
        return self.complete(prompt, formatted, **kwargs)

    def stream_complete(self, prompt, formatted=False, **kwargs):
        yield self.complete(prompt, formatted, **kwargs)

    async def astream_complete(self, prompt, formatted=False, **kwargs):
        response = self.complete(prompt, formatted, **kwargs)

        async def stream():
            yield response

        return stream()

    def _prepare_chat_with_tools(
        self, tools, user_msg=None, chat_history=None, **kwargs
    ):
        messages = list(chat_history or [])
        if user_msg is not None:
            if isinstance(user_msg, str):
                user_msg = ChatMessage(role=MessageRole.USER, content=user_msg)
            messages.append(user_msg)
        # Tool names and descriptions are part of what a provider receives.
        return {
            "messages": messages,
            "tools": [tool.metadata.to_openai_tool() for tool in tools],
        }

    def get_tool_calls_from_response(
        self, response, error_on_no_tool_call=True, **kwargs
    ):
        return [
            ToolSelection(
                tool_id=block.tool_call_id,
                tool_name=block.tool_name,
                tool_kwargs=block.tool_kwargs,
            )
            for block in response.message.blocks
            if isinstance(block, ToolCallBlock)
        ]
