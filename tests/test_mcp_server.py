"""Tests for the MCP order server, each against a real child process.

Nothing here calls the tool functions directly: every call goes through the
MCP client, over stdio, to a server started for the test.
"""

import asyncio
import hashlib
import inspect
import os
import sqlite3

import pytest

from src import messages
from src.guardrails.pii import hash_id
from src.mcp_server import server as server_module
from src.mcp_server.client import OrdersClient, call_tool
from src.mcp_server.server import MODEL_TOOLS
from src.tools.eligibility import check_return_eligibility
from src.tools.escalation import escalate_to_human
from src.tools.orders import get_order_status, list_customer_orders
from src.tools.return_requests import create_return_request
from tests.synthetic_data import ALICE, BOB

NOT_FOUND = {"error": "NOT_FOUND", "message": messages.ORDER_NOT_FOUND}
NOTHING_PENDING = {"error": "NOTHING_PENDING", "message": messages.NOTHING_PENDING}
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


def test_server_offers_model_control_tools(synthetic_db_path):
    tools = with_server(synthetic_db_path, lambda orders: orders.tools())

    assert set(tools) == set(MODEL_TOOLS) | CONTROL_TOOLS
    assert MODEL_TOOLS == (
        "get_order_status",
        "list_customer_orders",
        "check_return_eligibility",
        "create_return_request",
        "escalate_to_human",
    )


def test_descriptions_are_the_docstrings(synthetic_db_path):
    tools = with_server(synthetic_db_path, lambda orders: orders.tools())

    for function in (
        get_order_status,
        list_customer_orders,
        check_return_eligibility,
        create_return_request,
        escalate_to_human,
    ):
        assert tools[function.__name__] == inspect.cleandoc(function.__doc__)
        assert len(tools[function.__name__]) <= 1024


def test_no_tool_takes_identity_or_token(synthetic_db_path):
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
    # Control tools take nothing from the caller, except the card that was
    # clicked (what the person saw) and the order the page typed.
    card = {"order", "reason", "refund_amount"}
    for name in CONTROL_TOOLS - {"alias_order_reference", "approve_pending"}:
        assert parameters[name] == set()
    assert parameters["approve_pending"] == card
    assert not any("token" in key for key in parameters["approve_pending"])


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


def test_ten_foreign_orders_not_found(synthetic_db_path):
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


def test_foreign_missing_unknown_same_answer(synthetic_db_path):
    async def scenario(orders):
        return [
            await orders.call("get_order_status", {"order_ref": order_ref})
            for order_ref in ("o_other_customer", "o_does_not_exist", "SIP-7")
        ]

    assert with_server(synthetic_db_path, scenario) == [NOT_FOUND] * 3


def test_list_has_only_own_orders(synthetic_db_path):
    async def scenario(orders):
        return await orders.call("list_customer_orders", {"limit": 20})

    listed = with_server(synthetic_db_path, scenario, customer=BOB)

    assert len(listed["orders"]) == 1


def test_eligibility_comes_from_rule_engine(synthetic_db_path):
    async def scenario(orders):
        return await orders.call(
            "check_return_eligibility",
            {"order_ref": "o_day15", "reason": "changed_mind"},
        )

    answer = with_server(synthetic_db_path, scenario)

    assert (answer["decision"], answer["rule"]) == ("NOT_ELIGIBLE_WINDOW", "R6")


def test_eligibility_asks_for_a_reason(synthetic_db_path):
    async def scenario(orders):
        return await orders.call("check_return_eligibility", {"order_ref": "o_day14"})

    assert with_server(synthetic_db_path, scenario)["error"] == "REASON_REQUIRED"


def test_session_info_has_hash_and_values(synthetic_db_path):
    info = with_server(synthetic_db_path, lambda orders: orders.session_info())

    assert info["personal_values"] == {"sao paulo": "[city]", "01310": "[zip]"}
    assert ALICE not in str(info)
    assert len(info["customer_hash"]) == 10
    # The server was given this process's key, so both hash alike.
    assert info["customer_hash"] == hash_id(ALICE)


# --- The session is kept for the life of the connection -------------------


def test_alias_works_in_the_next_call(synthetic_db_path):
    async def scenario(orders):
        first = await orders.call("get_order_status", {"order_ref": "o_day14"})
        again = await orders.call("get_order_status", {"order_ref": first["order"]})
        return first, again

    first, again = with_server(synthetic_db_path, scenario)

    assert first["order"] == "SIP-1"
    assert again == first


def test_typed_number_gets_a_working_alias(synthetic_db_path):
    async def scenario(orders):
        alias = await orders.alias_order_reference("  O_DAY14 ")
        return alias, await orders.call("get_order_status", {"order_ref": alias})

    alias, answer = with_server(synthetic_db_path, scenario)

    assert alias == "SIP-1"
    assert answer["order"] == "SIP-1"
    assert answer["delivered_on"] == "2018-08-18"


def test_foreign_alias_ends_in_not_found(synthetic_db_path):
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


def test_unapproved_write_is_refused(synthetic_db_path):
    async def scenario(orders):
        return [await orders.call("create_return_request", RETURN) for _ in range(3)]

    answers = with_server(synthetic_db_path, scenario)

    assert [answer["error"] for answer in answers] == ["APPROVAL_REQUIRED"] * 3
    assert request_count(synthetic_db_path) == 2


def test_pending_request_uses_an_alias(synthetic_db_path):
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
        card = await orders.pending_approval()
        created = await orders.approve_pending(card)
        return (
            created,
            await orders.pending_approval(),
            await orders.approve_pending(card),
        )

    created, pending_after, second_approval = with_server(synthetic_db_path, scenario)

    assert created["return_request_id"] == 3
    assert created["status"] == "PENDING_REVIEW"
    assert pending_after is None
    assert second_approval == NOTHING_PENDING
    assert request_count(synthetic_db_path) == 3


def test_declining_writes_nothing(synthetic_db_path):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        card = await orders.pending_approval()
        declined = await orders.decline_pending()
        return declined, await orders.approve_pending(card)

    declined, approval_after = with_server(synthetic_db_path, scenario)

    assert declined == {"declined": True}
    assert approval_after == NOTHING_PENDING
    assert request_count(synthetic_db_path) == 2


def test_approve_without_pending_writes_none(synthetic_db_path):
    answer = with_server(synthetic_db_path, lambda orders: orders.approve_pending(None))

    assert answer == NOTHING_PENDING
    assert request_count(synthetic_db_path) == 2


def test_no_answer_holds_the_token(synthetic_db_path):
    async def scenario(orders):
        asked = await orders.call("create_return_request", RETURN)
        pending = await orders.pending_approval()
        created = await orders.approve_pending(pending)
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


# --- Least privilege of the server's connection ------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders (order_id) VALUES ('x')",
        "UPDATE return_requests SET refund_amount = 1000",
        "UPDATE return_requests SET status = 'APPROVED'",
        "DELETE FROM return_requests",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "PRAGMA table_info(orders)",
    ],
)
def test_connection_writes_only_new_rows(synthetic_db_path, sql):
    before = hashlib.sha256(synthetic_db_path.read_bytes()).hexdigest()
    conn = server_module.connect_for_order_server(str(synthetic_db_path))

    with pytest.raises(sqlite3.DatabaseError, match="not authorized"), conn:
        conn.execute(sql)
    conn.close()

    assert hashlib.sha256(synthetic_db_path.read_bytes()).hexdigest() == before


def test_connection_still_writes_rows(synthetic_db_path):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        written = await orders.approve_pending(await orders.pending_approval())
        ticket = await orders.call(
            "escalate_to_human", {"summary": "Müşteri bir temsilci istiyor."}
        )
        return written, ticket

    before = request_count(synthetic_db_path)
    written, ticket = with_server(synthetic_db_path, scenario)

    assert "error" not in written and "error" not in ticket
    assert request_count(synthetic_db_path) == before + 1


def test_failing_tool_gives_no_detail(tmp_path):
    """The SDK keeps the error and its traceback in the server process; the
    agent, and so the model, only learns that the tool failed."""
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()

    async def scenario(orders):
        return await orders.call("get_order_status", {"order_ref": "SIP-1"})

    with pytest.raises(RuntimeError) as failure:
        with_server(empty, scenario)

    text = str(failure.value)
    assert "Error executing tool get_order_status" in text
    assert "no such table" not in text and str(empty) not in text


# --- The click is bound to the card the person saw --------------------------


OTHER_RETURN = {"order_ref": "o_late_10", "reason": "late", "amount": "115.00"}


def test_stale_card_click_writes_nothing(
    synthetic_db_path,
):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        shown = await orders.pending_approval()
        # While the person looks at that card, another request is made.
        await orders.call("create_return_request", OTHER_RETURN)
        waiting = await orders.pending_approval()
        answer = await orders.approve_pending(shown)
        return shown, waiting, answer, await orders.pending_approval()

    shown, waiting, answer, after = with_server(synthetic_db_path, scenario)

    assert shown["order"] != waiting["order"] or shown["reason"] != waiting["reason"]
    assert answer["error"] == "STALE_CARD"
    # Nothing was written and nothing waits any more: the person asks again.
    assert request_count(synthetic_db_path) == 2
    assert after is None


@pytest.mark.parametrize(
    "change",
    [
        {"order": "SIP-9"},
        {"reason": "changed_mind"},
        {"refund_amount": "999.00"},
        {"order": ""},
    ],
)
def test_any_card_difference_is_stale(synthetic_db_path, change):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        card = {**await orders.pending_approval(), **change}
        return await orders.approve_pending(card)

    answer = with_server(synthetic_db_path, scenario)

    assert answer["error"] == "STALE_CARD"
    assert request_count(synthetic_db_path) == 2


def test_a_click_with_no_card_writes_nothing(synthetic_db_path):
    async def scenario(orders):
        await orders.call("create_return_request", RETURN)
        return await orders.approve_pending(None)

    answer = with_server(synthetic_db_path, scenario)

    assert answer["error"] == "STALE_CARD"
    assert request_count(synthetic_db_path) == 2
