"""One chat session of the user interface, kept alive between page runs.

The page framework runs the whole page script again on every click, but a
customer session needs things that must outlive a click: the conversation,
and the connection to the order server, which has to be opened, used and
closed inside one task.

So each session gets a background thread with its own event loop. One task
on that loop opens the session and then waits for work; the page hands it a
question and blocks until the answer is there. Closing the session ends
that task, which closes the connection and with it the server process.
"""

import asyncio
import logging
import threading
import weakref
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from pathlib import Path

from llama_index.core.llms.function_calling import FunctionCallingLLM

from src.knowledge.policy_index import PolicyIndex
from src.mcp_server.client import OrdersClient
from src.orchestrator import Answer, Orchestrator, SessionType
from src.tools.escalation import EscalationQueue

logger = logging.getLogger(__name__)

# How long the page waits for the session to start and for one answer.
START_TIMEOUT_SECONDS = 60
ANSWER_TIMEOUT_SECONDS = 120

Job = Callable[[Orchestrator], Awaitable[object]]


class SessionClosed(RuntimeError):
    """The session was closed and can take no more work."""


def stop(loop: asyncio.AbstractEventLoop, jobs: asyncio.Queue) -> None:
    """Tell the session's task to finish; safe to call from any thread."""
    if not loop.is_closed():
        loop.call_soon_threadsafe(jobs.put_nowait, None)


class ChatSession:
    def __init__(
        self,
        db_path: Path | str,
        policy_index: PolicyIndex | None = None,
        customer_unique_id: str | None = None,
        provider_llm: FunctionCallingLLM | None = None,
    ) -> None:
        """Open a customer session, or an operations session without a customer.

        The session type is fixed here and cannot be changed afterwards.
        """
        self.session_type = (
            SessionType.CUSTOMER if customer_unique_id else SessionType.OPS
        )
        self._db_path = db_path
        self._policy_index = policy_index
        self._customer = customer_unique_id
        self._provider_llm = provider_llm
        self._closed = False

        self._loop = asyncio.new_event_loop()
        self._jobs: asyncio.Queue = asyncio.Queue()
        self._started: Future = Future()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        # If the page forgets the session, the task still gets its signal.
        self._finalizer = weakref.finalize(self, stop, self._loop, self._jobs)
        try:
            self._started.result(timeout=START_TIMEOUT_SECONDS)
        except BaseException:
            self.close()
            raise

    # --- The background thread ---------------------------------------------

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as failure:
            if not self._started.done():
                self._started.set_exception(failure)
            else:
                logger.exception("chat session stopped with an error")
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        """Open the session and work until told to stop, all in one task."""
        if self.session_type is SessionType.CUSTOMER:
            async with OrdersClient(self._db_path, self._customer) as orders:
                router = await Orchestrator.for_customer(
                    orders,
                    self._customer,
                    self._policy_index,
                    EscalationQueue(),
                    self._provider_llm,
                )
                await self._work(router)
        else:
            router = Orchestrator.for_ops(self._db_path, self._provider_llm)
            try:
                await self._work(router)
            finally:
                router.close()

    async def _work(self, router: Orchestrator) -> None:
        self._started.set_result(None)
        while True:
            item = await self._jobs.get()
            if item is None:
                return
            job, done = item
            try:
                done.set_result(await job(router))
            except Exception as failure:  # noqa: BLE001
                # Whatever went wrong belongs to the caller that is waiting.
                done.set_exception(failure)

    def _do(self, job: Job) -> object:
        """Run a job on the session's task and wait for what it returns."""
        if self._closed:
            raise SessionClosed("the chat session is closed")
        done: Future = Future()
        self._loop.call_soon_threadsafe(self._jobs.put_nowait, (job, done))
        return done.result(timeout=ANSWER_TIMEOUT_SECONDS)

    # --- What the page calls -----------------------------------------------

    def ask(self, message: str) -> Answer:
        return self._do(lambda router: router.ask(message))

    def approve(self) -> str:
        """The person pressed approve: have the request written."""
        return self._do(lambda router: router.approve())

    def decline(self) -> str:
        return self._do(lambda router: router.decline())

    def close(self) -> None:
        """End the session: the connection closes and the server stops."""
        if self._closed:
            return
        self._closed = True
        self._finalizer()
        self._thread.join(timeout=START_TIMEOUT_SECONDS)

    @property
    def closed(self) -> bool:
        return self._closed
