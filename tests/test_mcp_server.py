"""Tests for the MCP server: started as a real child process over stdio."""

import asyncio
import sys

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.mcp_server import server as server_module
from src.mcp_server.client import PROJECT_ROOT, SERVER_MODULE, call_tool


def test_status_tool_answers_from_a_child_process():
    answer = call_tool("status")

    assert answer["server"] == "marketdesk-orders"
    assert answer["status"] == "ok"
    assert answer["memory_mb"] > 0


def test_server_lists_its_tools_over_stdio():
    async def tool_names():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", SERVER_MODULE], cwd=PROJECT_ROOT
        )
        async with (
            stdio_client(parameters) as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            return [tool.name for tool in tools.tools]

    assert asyncio.run(tool_names()) == ["status"]


def test_unknown_tool_is_an_error():
    with pytest.raises(RuntimeError, match="no_such_tool"):
        call_tool("no_such_tool")


def test_status_function_itself():
    answer = server_module.status()

    assert set(answer) == {"server", "status", "memory_mb"}
    assert answer["status"] == "ok"
