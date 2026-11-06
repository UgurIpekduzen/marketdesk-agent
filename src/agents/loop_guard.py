"""Stops an agent from calling tools again and again within one message.

Within one user message a call may be made twice: the third identical call
is not run, and the model gets an error telling it to stop repeating and
answer with what it has. All tool calls of a message together, identical
or not, are limited too: past config.MAX_TOOL_CALLS_PER_MESSAGE no tool is
run, so a message cannot run slow queries or pull large tables without end,
even when the model asks for many calls in one step. The counts start again
with every new user message.
"""

import json
from collections import Counter

import config

MAX_IDENTICAL_CALLS = 2

REPEATED_CALL = {
    "error": "REPEATED_CALL",
    "message": (
        "This tool was already called twice with the same arguments. Do not "
        "call it again: answer with the results you have, or hand the case "
        "to a human."
    ),
}

TOOL_LIMIT = {
    "error": "TOOL_LIMIT",
    "message": (
        "The tool calls allowed for this message are used up. Do not call any "
        "tool again: answer with the results you have, or hand the case to a "
        "human."
    ),
}


class LoopGuard:
    """Counts tool calls in one message and stops repeats and runaway loops."""

    def __init__(
        self,
        max_identical_calls: int = MAX_IDENTICAL_CALLS,
        max_calls: int = config.MAX_TOOL_CALLS_PER_MESSAGE,
    ) -> None:
        self._max_identical = max_identical_calls
        self._max_calls = max_calls
        self._calls: Counter = Counter()

    def reset(self) -> None:
        """Forget all calls; called at the start of every user message."""
        self._calls.clear()

    def refusal(self, tool_name: str, arguments: dict) -> dict | None:
        """Count this call; the error to answer instead, or None to run it.

        Args:
            tool_name (str): The tool the model wants to call.
            arguments (dict): Its arguments.

        Returns:
            The error to answer instead of running the tool, or None to run it.
        """
        # Sorted keys, so the order the model wrote the arguments in is irrelevant.
        key = (tool_name, json.dumps(arguments, sort_keys=True, default=str))
        self._calls[key] += 1
        if self._calls.total() > self._max_calls:
            return TOOL_LIMIT
        if self._calls[key] > self._max_identical:
            return REPEATED_CALL
        return None
