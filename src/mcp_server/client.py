"""Starts the MCP server as a child process and calls one of its tools."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVER_MODULE = "src.mcp_server.server"


async def call_tool_async(name: str, arguments: dict | None = None) -> dict:
    """Start the server, call one tool, stop the server, return the result."""
    parameters = StdioServerParameters(
        # The same interpreter as this process, so the same packages.
        command=sys.executable,
        args=["-m", SERVER_MODULE],
        cwd=PROJECT_ROOT,
    )
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments or {})
    if result.is_error:
        raise RuntimeError(f"tool {name!r} failed: {result.content}")
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


def call_tool(name: str, arguments: dict | None = None) -> dict:
    """call_tool_async for callers that are not async themselves."""
    return asyncio.run(call_tool_async(name, arguments))
