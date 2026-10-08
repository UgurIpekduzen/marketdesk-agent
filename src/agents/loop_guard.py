"""Stops an agent from calling the same tool with the same arguments again
and again.

Within one user message a call may be made twice. The third identical call
is not run: the model gets an error instead, telling it to stop repeating
and answer with what it has. The count starts again with every new user
message.
"""

import json
from collections import Counter

MAX_IDENTICAL_CALLS = 2

REPEATED_CALL = {
    "error": "REPEATED_CALL",
    "message": (
        "This tool was already called twice with the same arguments. Do not "
        "call it again: answer with the results you have, or hand the case "
        "to a human."
    ),
}


class LoopGuard:
    def __init__(self, max_identical_calls: int = MAX_IDENTICAL_CALLS) -> None:
        self._max = max_identical_calls
        self._calls: Counter = Counter()

    def reset(self) -> None:
        """Forget all calls; called at the start of every user message."""
        self._calls.clear()

    def allows(self, tool_name: str, arguments: dict) -> bool:
        """Count this call and say whether it may run."""
        # Sorted keys, so the order the model wrote the arguments in is irrelevant.
        key = (tool_name, json.dumps(arguments, sort_keys=True, default=str))
        self._calls[key] += 1
        return self._calls[key] <= self._max
