"""Tests for the MCP order server, each against a real child process.

Nothing here calls the tool functions directly: every call goes through the
MCP client, over stdio, to a server started for the test.
"""

import asyncio
import inspect
import os
import sqlite3

import pytest

from src import messages
from src.mcp_server import server as server_module
from src.mcp_server.client import OrdersClient, call_tool
from src.mcp_server.server import MODEL_TOOLS
from src.tools.eligibility import check_return_eligibility
from src.tools.orders import get_order_status, list_customer_orders
from src.tools.return_requests import create_return_request
from tests.synthetic_data import ALICE, BOB

NOT_FOUND = {"error": "NOT_FOUND", "message": messages.ORDER_NOT_FOUND}
CONTROL_TOOLS = {
    "status",
    "session_info",
    "alias_order_reference",
    "pending_approval",
    "approve_pending",
    "decline_pending",
}
RETURN = {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"}


def with_server(db_path, scenario, customer=ALICE):
    """Start a server for the customer, run the scenario, stop the server."""

    async def run():
        async with OrdersClient(db_path, customer) as orders:
            return await scenario(orders)

    return asyncio.run(run())


def request_count(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0]
    finally:
        conn.close()


# --- What the server offers ----------------------------------------------


def test_server_offers_the_four_order_tools_and_the_control_tools(synthetic_db_path):
    tools = with_server(synthetic_db_path, lambda orders: orders.tools())

    assert set(tools) == set(MODEL_TOOLS) | CONTROL_TOOLS
    assert MODEL_TOOLS == (
        "get_order_status",
        "list_customer_orders",
        "check_return_eligibility",
        "create_return_request",
    )


def test_descriptions_are_the_docstrings_of_the_wrapped_functions(synthetic_db_path):
    tools = with_server(synthetic_db_path, lambda orders: orders.tools())

    for function in (
        get_order_status,
        list_customer_orders,
        check_return_eligibility,
        create_return_request,
    ):
        assert tools[function.__name__] == inspect.cleandoc(function.__doc__)
        assert len(tools[function.__name__]) <= 1024


def test_no_order_tool_takes_identity_or_an_approval_token(synthetic_db_path):
    async def schemas(orders):
        listed = await orders._session.list_tools()
        return {
            tool.name: set(tool.input_schema["properties"]) for tool in listed.tools
        }

    parameters = with_server(synthetic_db_path, schemas)

    assert parameters["get_order_status"] == {"order_ref"}
    assert parameters["list_customer_orders"] == {"limit", "status"}
    assert parameters["check_return_eligibility"] == {"order_ref", "reason"}
    assert parameters["create_return_request"] == {"order_ref", "reason", "amount"}
    for name in CONTROL_TOOLS - {"alias_order_reference"}:
        assert parameters[name] == set()


def test_server_runs_in_another_process(synthetic_db_path):
    async def scenario(orders):
        return (await orders.call("status"))["memory_mb"], os.getpid()

    memory, _ = with_server(synthetic_db_path, scenario)

    # The server reports its own memory, far below this test process's.
    assert 0 < memory < server_module.memory_mb() * 2
    assert server_module._state is None  # no session was opened in this process


def test_status_needs_no_session():
    assert call_tool("status")["status"] == "ok"


def test_unknown_tool_is_an_error():
    with pytest.raises(RuntimeError, match="no_such_tool"):
        call_tool("no_such_tool")


def test_closed_client_refuses_calls(synthetic_db_path):
    orders = OrdersClient(synthetic_db_path, ALICE)

    with pytest.raises(RuntimeError, match="not open"):
        asyncio.run(orders.call("status"))


# --- Identity lives on the server ----------------------------------------


def test_own_order_is_found(synthetic_db_path):
    async def scenario(orders):
        return await orders.call("get_order_status", {"order_ref": "o_two_items"})

    answer = with_server(synthetic_db_path, scenario)

    assert answer["order"] == "SIP-1"
    assert answer["status"] == "delivered"
    assert answer["items_total"] == "165.00"


def test_ten_foreign_orders_are_all_not_found(synthetic_db_path):
    conn = sqlite3.connect(synthetic_db_path)
    alice_orders = [
        row[0]
        for row in conn.execute(
            "SELECT o.order_id FROM orders AS o "
            "JOIN customers AS c ON c.customer_id = o.customer_id "
            "WHERE c.customer_unique_id = ? ORDER BY o.order_id LIMIT 10",
            (ALICE,),
        )
    ]
    conn.close()

    async def scenario(orders):
        return [
            await orders.call("get_order_status", {"order_ref": order_id})
            for order_id in alice_orders
        ]

    answers = with_server(synthetic_db_path, scenario, customer=BOB)

    assert len(alice_orders) == 10
    assert answers == [NOT_FOUND] * 10


def test_foreign_missing_and_unknown_alias_give_the_same_answer(synthetic_db_path):
    async def scenario(orders):
        return [
            await orders.call("get_order_status", {"order_ref": order_ref})
            for order_ref in ("o_other_customer", "o_does_not_exist", "SIP-7")
        ]

    assert with_server(synthetic_db_path, scenario) == [NOT_FOUND] * 3


def test_list_holds_only_the_customers_own_orders(synthetic_db_path):
    async def scenario(orders):
        return await orders.call("list_customer_orders", {"limit": 20})

    listed = with_server(synthetic_db_path, scenario, customer=BOB)

    assert len(listed["orders"]) == 1


def test_eligibility_comes_from_the_rule_engine(synthetic_db_path):
    async def scenario(orders):
        return await orders.call(
            "check_return_eligibility",
            {"order_ref": "o_day15", "reason": "changed_mind"},
        )

    answer = with_server(synthetic_db_path, scenario)

    assert (answer["decision"], answer["rule"]) == ("NOT_ELIGIBLE_WINDOW", "R6")


def test_session_info_gives_a_hash_and_the_personal_values(synthetic_db_path):
    info = with_server(synthetic_db_path, lambda orders: orders.session_info())

    assert info["personal_values"] == {"sao paulo": "[city]", "01310": "[zip]"}
    assert ALICE not in str(info)
    assert len(info["customer_hash"]) == 10


# --- The session is kept for the life of the connection -------------------


def test_alias_from_one_call_works_in_the_next(synthetic_db_path):
    async def scenario(orders):
        first = await orders.call("get_order_status", {"order_ref": "o_day14"})
        again = await orders.call("get_order_status", {"order_ref": first["order"]})
        return first, again

    first, again = with_server(synthetic_db_path, scenario)

    assert first["order"] == "SIP-1"
    assert again == first


def test_typed_order_number_gets_an_alias_the_tools_resolve(synthetic_db_path):
    async def scenario(orders):
        alias = await orders.alias_order_reference("  O_DAY14 ")
        return alias, await orders.call("get_order_status", {"order_ref": alias})

    alias, answer = with_server(synthetic_db_path, scenario)

    assert alias == "SIP-1"
    assert answer["order"] == "SIP-1"
    assert answer["delivered_on"] == "2018-08-18"


def test_alias_of_a_foreign_order_still_ends_in_not_found(synthetic_db_path):
    async def scenario(orders):
        alias = await orders.alias_order_reference("o_other_customer")
        return await orders.call("get_order_status", {"order_ref": alias})

    assert with_server(synthetic_db_path, scenario) == NOT_FOUND


def test_two_servers_are_two_sessions(synthetic_db_path):
    async def scenario(first):
        async with OrdersClient(synthetic_db_path, ALICE) as second:
            await first.call("get_order_status", {"order_ref": "o_day14"})
            await first.call("create_return_request", RETURN)
            return (
                await second.call("get_order_status", {"order_ref": "SIP-1"}),
                await second.pending_approval(),
                await first.pending_approval(),
            )

    alias_elsewhere, pending_elsewhere, pending_here = with_server(
        synthetic_db_path, scenario
    )

    assert alias_elsewhere == NOT_FOUND
    assert pending_elsewhere is None
    assert pending_here["order"] == "SIP-1"


# --- Approval is checked on the server ------------------------------------


def test_write_without_approval_is_refused_and_writes_nothing(synthetic_db_path):
    async def scenario(orders):
        return [await orders.call("create_return_request", RETURN) for _ in range(3)]

    answers = with_server(synthetic_db_path, scenario)

    assert [answer["error"] for answer in answers] == ["APPROVAL_REQUIRED"] * 3
    assert request_count(synthetic_db_path) == 2


def test_pending_request_is_described_with_an_alias(synthetic_db_path):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        return await orders.pending_approval()

    assert with_server(synthetic_db_path, scenario) == {
        "pending": True,
        "order": "SIP-1",
        "reason": "damaged",
        "refund_amount": "115.00",
        "request_status": "PENDING_REVIEW",
    }


def test_approval_writes_exactly_one_row(synthetic_db_path):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        created = await orders.approve_pending()
        return created, await orders.pending_approval(), await orders.approve_pending()

    created, pending_after, second_approval = with_server(synthetic_db_path, scenario)

    assert created["return_request_id"] == 3
    assert created["status"] == "PENDING_REVIEW"
    assert pending_after is None
    assert second_approval == {"error": "NOTHING_PENDING"}
    assert request_count(synthetic_db_path) == 3


def test_declining_writes_nothing(synthetic_db_path):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        declined = await orders.decline_pending()
        return declined, await orders.approve_pending()

    declined, approval_after = with_server(synthetic_db_path, scenario)

    assert declined == {"declined": True}
    assert approval_after == {"error": "NOTHING_PENDING"}
    assert request_count(synthetic_db_path) == 2


def test_approving_with_nothing_pending_writes_nothing(synthetic_db_path):
    answer = with_server(synthetic_db_path, lambda orders: orders.approve_pending())

    assert answer == {"error": "NOTHING_PENDING"}
    assert request_count(synthetic_db_path) == 2


def test_no_answer_ever_holds_the_approval_token(synthetic_db_path):
    async def scenario(orders):
        asked = await orders.call("create_return_request", RETURN)
        pending = await orders.pending_approval()
        created = await orders.approve_pending()
        return [asked, pending, created]

    answers = with_server(synthetic_db_path, scenario)

    for answer in answers:
        assert "token" not in str(answer).lower()


def test_foreign_order_cannot_be_returned(synthetic_db_path):
    async def scenario(orders):
        asked = await orders.call(
            "create_return_request", {**RETURN, "order_ref": "o_other_customer"}
        )
        return asked, await orders.pending_approval()

    asked, pending = with_server(synthetic_db_path, scenario)

    assert asked == NOT_FOUND
    assert pending is None
