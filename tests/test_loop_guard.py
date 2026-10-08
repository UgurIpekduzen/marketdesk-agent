"""Tests for the guard against repeated tool calls."""

from src.agents.loop_guard import MAX_IDENTICAL_CALLS, REPEATED_CALL, LoopGuard


def test_a_call_may_be_made_twice_but_not_a_third_time():
    guard = LoopGuard()
    call = ("get_order_status", {"order_ref": "SIP-1"})

    assert [guard.allows(*call) for _ in range(4)] == [True, True, False, False]
    assert MAX_IDENTICAL_CALLS == 2


def test_other_arguments_are_another_call():
    guard = LoopGuard()
    for _ in range(2):
        guard.allows("get_order_status", {"order_ref": "SIP-1"})

    assert guard.allows("get_order_status", {"order_ref": "SIP-2"})
    assert guard.allows("check_return_eligibility", {"order_ref": "SIP-1"})


def test_argument_order_does_not_matter():
    guard = LoopGuard()
    guard.allows("check_return_eligibility", {"order_ref": "SIP-1", "reason": "late"})
    guard.allows("check_return_eligibility", {"reason": "late", "order_ref": "SIP-1"})

    assert not guard.allows(
        "check_return_eligibility", {"order_ref": "SIP-1", "reason": "late"}
    )


def test_count_starts_again_after_a_reset():
    guard = LoopGuard()
    for _ in range(3):
        guard.allows("list_customer_orders", {})

    guard.reset()

    assert guard.allows("list_customer_orders", {})


def test_the_limit_can_be_set():
    guard = LoopGuard(max_identical_calls=1)

    assert guard.allows("search_policies", {"query": "iade"})
    assert not guard.allows("search_policies", {"query": "iade"})


def test_refusal_tells_the_model_what_to_do():
    assert REPEATED_CALL["error"] == "REPEATED_CALL"
    assert "Do not call it again" in REPEATED_CALL["message"]
