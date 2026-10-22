"""Counts what one agent run cost: model calls, tool calls and tokens.

A run is everything that happens for one user message. The counts are
logged as one line; the customer appears as a short hash, never as the id.
"""

import json
import logging
from dataclasses import dataclass, field

from src.guardrails.pii import hash_id

logger = logging.getLogger(__name__)

# Where providers put token counts in a raw response. Gemini uses the first
# pair, OpenAI-style APIs such as Groq the second.
INPUT_TOKEN_KEYS = ("prompt_token_count", "prompt_tokens")
OUTPUT_TOKEN_KEYS = ("candidates_token_count", "completion_tokens")
USAGE_KEYS = ("usage_metadata", "usage")


def first_number(usage: dict, keys: tuple[str, ...]) -> int:
    for key in keys:
        if isinstance(usage.get(key), int):
            return usage[key]
    return 0


def token_usage(raw: object) -> tuple[int, int]:
    """(input tokens, output tokens) of one raw model response, or (0, 0)."""
    if not isinstance(raw, dict):
        return 0, 0
    for key in USAGE_KEYS:
        usage = raw.get(key)
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        if isinstance(usage, dict):
            return (
                first_number(usage, INPUT_TOKEN_KEYS),
                first_number(usage, OUTPUT_TOKEN_KEYS),
            )
    return 0, 0


@dataclass
class RunLog:
    llm_calls: int = 0
    tool_calls: list[str] = field(default_factory=list)
    # The arguments of each call, for a person inspecting a run. They are
    # kept here only and are not part of the log line.
    tool_arguments: list[dict] = field(default_factory=list)
    # What each tool answered, in the order the answers came back. Like the
    # arguments, kept for inspection and evaluation only, never logged.
    tool_results: list[tuple[str, object]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped_at_step_limit: bool = False
    # Tools the model asked for that the agent was not given.
    unknown_tools: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        """The error codes the tools answered, and UNKNOWN_TOOL, in order."""
        codes = [
            result["error"]
            for _, result in self.tool_results
            if isinstance(result, dict) and isinstance(result.get("error"), str)
        ]
        return codes + ["UNKNOWN_TOOL"] * len(self.unknown_tools)

    @property
    def steps(self) -> int:
        """Model calls plus tool calls."""
        return self.llm_calls + len(self.tool_calls)

    def add_llm_call(self, raw: object) -> None:
        self.llm_calls += 1
        input_tokens, output_tokens = token_usage(raw)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def add_tool_call(self, tool_name: str, arguments: dict | None = None) -> None:
        self.tool_calls.append(tool_name)
        self.tool_arguments.append(arguments or {})

    def add_tool_result(self, tool_name: str, content: str) -> None:
        """Keep a tool's answer: parsed when it is JSON, as text otherwise."""
        try:
            result: object = json.loads(content)
        except ValueError:
            result = content
        self.tool_results.append((tool_name, result))

    def write(self, agent: str, customer_unique_id: str | None) -> None:
        """Log the run as one line."""
        logger.info(
            "run agent=%s customer=%s steps=%d llm_calls=%d tool_calls=%d "
            "tools=%s errors=%s input_tokens=%d output_tokens=%d step_limit=%s",
            agent,
            hash_id(customer_unique_id) if customer_unique_id else "-",
            self.steps,
            self.llm_calls,
            len(self.tool_calls),
            ",".join(self.tool_calls) or "-",
            ",".join(self.errors) or "-",
            self.input_tokens,
            self.output_tokens,
            self.stopped_at_step_limit,
        )
