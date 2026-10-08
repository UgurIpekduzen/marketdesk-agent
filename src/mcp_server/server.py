"""The project's own MCP server for the order tools, run over stdio.

Start it with:  python -m src.mcp_server.server

One server process serves one signed-in customer. The application starts
it with the customer and the database in two environment variables, and the
process keeps the session for as long as it lives: who the customer is, the
order aliases, and the approval of a return request. None of that is ever
an argument of a tool, so the model cannot supply or change it.

Two groups of tools:

- the four order tools the model may call. They are the same functions the
  rest of the project uses; this file only wraps them;
- control tools for the application's own code: turning an order number the
  customer typed into an alias, and showing, approving or declining a
  pending return request. They are never handed to the model. The approval
  token is made and checked here and does not leave this process.
"""

import inspect
import os
import sqlite3
from dataclasses import dataclass
from datetime import date

from mcp.server.mcpserver import MCPServer

import config
from src.guardrails.pii import hash_id
from src.tools.eligibility import check_return_eligibility
from src.tools.orders import DEFAULT_LIST_LIMIT, get_order_status, list_customer_orders
from src.tools.return_requests import create_return_request
from src.tools.session import Session, open_session

SERVER_NAME = "marketdesk-orders"
CUSTOMER_VARIABLE = "MARKETDESK_CUSTOMER"
DB_VARIABLE = "MARKETDESK_DB"

# The tools the model may be given. Everything else is for application code.
MODEL_TOOLS = (
    "get_order_status",
    "list_customer_orders",
    "check_return_eligibility",
    "create_return_request",
)

server = MCPServer(SERVER_NAME)


@dataclass
class State:
    session: Session
    conn: sqlite3.Connection
    simulated_today: date


_state: State | None = None


def state() -> State:
    """The session of this process, opened on first use."""
    global _state
    if _state is None:
        conn = sqlite3.connect(os.environ[DB_VARIABLE])
        _state = State(
            session=open_session(conn, os.environ[CUSTOMER_VARIABLE]),
            conn=conn,
            simulated_today=config.SIMULATED_TODAY,
        )
    return _state


def describe(function) -> str:
    """The description the model reads: the wrapped function's docstring."""
    return inspect.cleandoc(function.__doc__)


def memory_mb() -> int:
    """Memory this process holds right now, in MB (Linux only; else 0)."""
    try:
        with open("/proc/self/status", encoding="ascii") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


# --- Order tools: what the model may call ---------------------------------


@server.tool(name="get_order_status", description=describe(get_order_status))
async def get_order_status_tool(order_ref: str) -> dict:
    current = state()
    return get_order_status(
        current.session, current.conn, order_ref, current.simulated_today
    )


@server.tool(name="list_customer_orders", description=describe(list_customer_orders))
async def list_customer_orders_tool(
    limit: int = DEFAULT_LIST_LIMIT, status: str | None = None
) -> dict:
    current = state()
    return list_customer_orders(
        current.session, current.conn, limit, status, current.simulated_today
    )


@server.tool(
    name="check_return_eligibility", description=describe(check_return_eligibility)
)
async def check_return_eligibility_tool(order_ref: str, reason: str) -> dict:
    current = state()
    return check_return_eligibility(
        current.session, current.conn, order_ref, reason, current.simulated_today
    )


@server.tool(name="create_return_request", description=describe(create_return_request))
async def create_return_request_tool(order_ref: str, reason: str, amount: str) -> dict:
    # No approval token among the arguments: a caller cannot pass one.
    current = state()
    return create_return_request(
        current.session,
        current.conn,
        order_ref,
        reason,
        amount,
        today=current.simulated_today,
    )


# --- Control tools: for the application's code, never for the model -------


@server.tool()
async def status() -> dict:
    """Report that the server is running, with the memory it uses in MB."""
    return {"server": SERVER_NAME, "status": "ok", "memory_mb": memory_mb()}


@server.tool()
async def session_info() -> dict:
    """Say whose session this is (as a hash) and which values are personal."""
    session = state().session
    return {
        "customer_hash": hash_id(session.customer_unique_id),
        "personal_values": session.personal_values,
    }


@server.tool()
async def alias_order_reference(order_ref: str) -> dict:
    """Return the session alias for an order number the customer typed.

    Any number gets an alias; whether the order is the customer's own is
    decided later, by the order tool that looks it up.
    """
    return {"alias": state().session.alias_for(order_ref.strip().lower())}


@server.tool()
async def pending_approval() -> dict:
    """Describe the return request that is waiting for the person's answer."""
    current = state()
    action = current.session.approvals.awaiting
    if action is None:
        return {"pending": False}
    decision = check_return_eligibility(
        current.session,
        current.conn,
        action.order_id,
        action.reason,
        current.simulated_today,
    )
    return {
        "pending": True,
        "order": current.session.alias_for(action.order_id),
        "reason": action.reason,
        "refund_amount": str(action.amount),
        "request_status": decision["request_status"],
    }


@server.tool()
async def approve_pending() -> dict:
    """The person said yes: write the pending return request."""
    current = state()
    action = current.session.approvals.awaiting
    if action is None:
        return {"error": "NOTHING_PENDING"}
    # The token is created, used and gone within this function.
    token = current.session.approvals.approve()
    return create_return_request(
        current.session,
        current.conn,
        action.order_id,
        action.reason,
        str(action.amount),
        token,
        current.simulated_today,
    )


@server.tool()
async def decline_pending() -> dict:
    """The person said no: drop the pending return request."""
    state().session.approvals.reject()
    return {"declined": True}


if __name__ == "__main__":
    server.run(transport="stdio")
