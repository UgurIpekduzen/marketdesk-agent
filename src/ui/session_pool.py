"""The chat sessions open in this server process, with two limits.

The page framework gives no signal when a visitor closes the tab, so a
session, and the order server process of a customer session, would stay
until the framework drops it. The pool closes a session nobody has used for
a while and refuses a new one while too many are open.
"""

import logging
import threading
import time
from collections.abc import Callable

from src.ui.chat_session import ChatSession

logger = logging.getLogger(__name__)

# How often the background check looks for idle sessions.
CHECK_SECONDS = 60


class SessionLimitReached(RuntimeError):
    """Too many sessions are open; the visitor should try again later."""


class SessionPool:
    def __init__(
        self,
        idle_seconds: float,
        max_open: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._idle_seconds = idle_seconds
        self._max_open = max_open
        self._clock = clock
        self._sessions: list[ChatSession] = []
        self._lock = threading.Lock()
        self._stopped = threading.Event()

    def open(self, start: Callable[[], ChatSession]) -> ChatSession:
        """Start a session with start(), unless the pool is full."""
        with self._lock:
            self._drop_idle()
            if len(self._sessions) >= self._max_open:
                raise SessionLimitReached(
                    f"{len(self._sessions)} chat sessions are open already"
                )
            # Started under the lock, so two visitors cannot both take the
            # last place.
            session = start()
            self._sessions.append(session)
            return session

    def close_idle(self) -> int:
        """Close the sessions idle for too long; how many were closed."""
        with self._lock:
            return self._drop_idle()

    def _drop_idle(self) -> int:
        now = self._clock()
        idle = [
            session
            for session in self._sessions
            if not session.closed and now - session.last_used > self._idle_seconds
        ]
        for session in idle:
            session.close()
        # Sessions the page closed itself leave the list here as well.
        self._sessions = [session for session in self._sessions if not session.closed]
        if idle:
            logger.info("closed %d idle chat sessions", len(idle))
        return len(idle)

    @property
    def open_count(self) -> int:
        with self._lock:
            return sum(not session.closed for session in self._sessions)

    def start_checking(self, every_seconds: float = CHECK_SECONDS) -> None:
        """Look for idle sessions in the background until stop() is called."""

        def check() -> None:
            while not self._stopped.wait(every_seconds):
                try:
                    self.close_idle()
                except Exception:
                    logger.exception("idle session check failed")

        threading.Thread(target=check, name="session-pool", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()
