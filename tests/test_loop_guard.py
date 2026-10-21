"""Tests for the guard against repeated and too many tool calls."""

import config
from src.agents.loop_guard import (
    MAX_IDENTICAL_CALLS,
    REPEATED_CALL,
    TOOL_LIMIT,
    LoopGuard,
)


def test_a_call_may_be_made_twice_but_not_a_third_time():
    guard = LoopGuard()
    call = ("get_order_status", {"order_ref": "SIP-1"})

    assert [guard.refusal(*call) for _ in range(4)] == [
        None,
        None,
        REPEATED_CALL,
        REPEATED_CALL,
    ]
    assert MAX_IDENTICAL_CALLS == 2


def test_other_arguments_are_another_call():
    guard = LoopGuard()
    for _ in range(2):
        guard.refusal("get_order_status", {"order_ref": "SIP-1"})

    assert guard.refusal("get_order_status", {"order_ref": "SIP-2"}) is None
    assert guard.refusal("check_return_eligibility", {"order_ref": "SIP-1"}) is None


def test_argument_order_does_not_matter():
    guard = LoopGuard()
    guard.refusal("check_return_eligibility", {"order_ref": "SIP-1", "reason": "late"})
    guard.refusal("check_return_eligibility", {"reason": "late", "order_ref": "SIP-1"})

    assert (
        guard.refusal(
            "check_return_eligibility", {"order_ref": "SIP-1", "reason": "late"}
        )
        == REPEATED_CALL
    )


def test_count_starts_again_after_a_reset():
    guard = LoopGuard()
    for _ in range(3):
        guard.refusal("list_customer_orders", {})

    guard.reset()

    assert guard.refusal("list_customer_orders", {}) is None


def test_the_limit_can_be_set():
    guard = LoopGuard(max_identical_calls=1)

    assert guard.refusal("search_policies", {"query": "iade"}) is None
    assert guard.refusal("search_policies", {"query": "iade"}) == REPEATED_CALL


def test_refusal_tells_the_model_what_to_do():
    assert REPEATED_CALL["error"] == "REPEATED_CALL"
    assert "Do not call it again" in REPEATED_CALL["message"]
    assert TOOL_LIMIT["error"] == "TOOL_LIMIT"
    assert "Do not call any tool again" in TOOL_LIMIT["message"]


def test_calls_past_the_limit_of_a_message_are_not_run():
    guard = LoopGuard()
    calls = [("run_sql", {"query": f"SELECT {n}"}) for n in range(20)]

    refusals = [guard.refusal(*call) for call in calls]

    allowed = config.MAX_TOOL_CALLS_PER_MESSAGE
    assert refusals == [None] * allowed + [TOOL_LIMIT] * (20 - allowed)
    assert allowed == 12


def test_the_limit_counts_repeated_calls_too():
    guard = LoopGuard(max_calls=3)
    call = ("list_metrics", {})

    assert [guard.refusal(*call) for _ in range(4)] == [
        None,
        None,
        REPEATED_CALL,
        TOOL_LIMIT,
    ]


def test_the_limit_starts_again_with_the_next_message():
    guard = LoopGuard(max_calls=2)
    for number in range(3):
        guard.refusal("run_sql", {"query": f"SELECT {number}"})

    guard.reset()

    assert guard.refusal("run_sql", {"query": "SELECT 9"}) is None
