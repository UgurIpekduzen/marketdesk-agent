"""How many questions all visitors together may ask in one hour.

Every question costs several model requests from one free-tier quota. A
limit per visitor would not hold: a new tab is a new visitor. So the limit
is shared by the whole server process.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 3600


class QuestionLimitReached(RuntimeError):
    """The questions of the last hour have used up the limit."""


class QuestionLimit:
    def __init__(
        self,
        per_hour: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._per_hour = per_hour
        self._clock = clock
        self._asked: deque[float] = deque()
        self._lock = threading.Lock()

    def take(self) -> None:
        """Count one question, or refuse it when the hour is full."""
        with self._lock:
            started = self._clock()
            while self._asked and started - self._asked[0] >= WINDOW_SECONDS:
                self._asked.popleft()
            if len(self._asked) >= self._per_hour:
                raise QuestionLimitReached(
                    f"{self._per_hour} questions in the last hour"
                )
            self._asked.append(started)
