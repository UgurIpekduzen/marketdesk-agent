"""The project's own MCP server, run as a separate process over stdio.

Start it with:  python -m src.mcp_server.server

For now it offers one tool, status, which shows that the server starts and
answers. The order tools are added to this same server later.
"""

from mcp.server.mcpserver import MCPServer

SERVER_NAME = "marketdesk-orders"

server = MCPServer(SERVER_NAME)


def memory_mb() -> int:
    """Memory this process holds right now, in MB (Linux only; else 0)."""
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


@server.tool()
def status() -> dict:
    """Report that the server is running, with the memory it uses in MB."""
    return {"server": SERVER_NAME, "status": "ok", "memory_mb": memory_mb()}


if __name__ == "__main__":
    server.run(transport="stdio")
