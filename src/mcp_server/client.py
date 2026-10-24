"""The application's side of the MCP connection to the order server.

OrdersClient starts the server as a child process for one customer and
keeps that one connection open until it is closed. It has to: the server
holds the session in memory, and a client that reconnected for every call
would get a new, empty session each time.

Use it as an async context manager, inside one task:

    async with OrdersClient(db_path, customer_unique_id) as orders:
        answer = await orders.call("get_order_status", {"order_ref": "SIP-1"})
"""

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Self

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.guardrails.pii import HASH_KEY_VARIABLE, hash_key
from src.i18n import DEFAULT_LANGUAGE, Language
from src.mcp_server.server import CUSTOMER_VARIABLE, DB_VARIABLE, LANGUAGE_VARIABLE

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVER_MODULE = "src.mcp_server.server"


def server_parameters(env: dict[str, str] | None = None) -> StdioServerParameters:
    return StdioServerParameters(
        # The same interpreter as this process, so the same packages.
        command=sys.executable,
        args=["-m", SERVER_MODULE],
        cwd=PROJECT_ROOT,
        env=env,
    )


def result_to_dict(name: str, result) -> dict:
    if result.is_error:
        raise RuntimeError(f"tool {name!r} failed: {result.content}")
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


class OrdersClient:
    def __init__(
        self,
        db_path: Path | str,
        customer_unique_id: str,
        language: Language = DEFAULT_LANGUAGE,
    ) -> None:
        # The customer and the language are given to the server once, when
        # it starts, and are never part of a tool call.
        self._parameters = server_parameters(
            {
                DB_VARIABLE: str(db_path),
                CUSTOMER_VARIABLE: customer_unique_id,
                LANGUAGE_VARIABLE: Language(language).value,
                # The same key as here, so both processes hash an id alike.
                HASH_KEY_VARIABLE: hash_key(),
            }
        )
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> Self:
        self._stack = AsyncExitStack()
        try:
            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(self._parameters)
            )
            self._session = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await self._session.initialize()
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        # Closing the connection ends the server process.
        await self._stack.aclose()
        self._stack = self._session = None

    async def call(self, name: str, arguments: dict | None = None) -> dict:
        """Call one tool on the server and return its result."""
        if self._session is None:
            raise RuntimeError("the connection to the order server is not open")
        result = await self._session.call_tool(name, arguments or {})
        return result_to_dict(name, result)

    async def tools(self) -> dict[str, str]:
        """The server's tools: name -> description."""
        listed = await self._session.list_tools()
        return {tool.name: tool.description for tool in listed.tools}

    # --- Control calls, made by application code only ---------------------

    async def session_info(self) -> dict:
        return await self.call("session_info")

    async def alias_order_reference(self, order_ref: str) -> str:
        answer = await self.call("alias_order_reference", {"order_ref": order_ref})
        return answer["alias"]

    async def pending_approval(self) -> dict | None:
        """The return request waiting for the person's answer, or None."""
        answer = await self.call("pending_approval")
        return answer if answer["pending"] else None

    async def approve_pending(self, card: dict | None) -> dict:
        """Approve the card the person saw (order, reason, refund_amount)."""
        card = card or {}
        return await self.call(
            "approve_pending",
            {
                "order": card.get("order", ""),
                "reason": card.get("reason", ""),
                "refund_amount": card.get("refund_amount", ""),
            },
        )

    async def decline_pending(self) -> dict:
        return await self.call("decline_pending")


async def call_tool_async(name: str, arguments: dict | None = None) -> dict:
    """Start a server without a session, call one tool, stop the server.

    Only for tools that need no session, such as status.
    """
    async with (
        stdio_client(server_parameters()) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments or {})
    return result_to_dict(name, result)


def call_tool(name: str, arguments: dict | None = None) -> dict:
    """call_tool_async for callers that are not async themselves."""
    return asyncio.run(call_tool_async(name, arguments))
