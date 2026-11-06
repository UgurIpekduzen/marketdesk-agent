"""Tests for the step and token log of an agent run."""

import logging
from types import SimpleNamespace

from src.agents.run_log import RunLog, token_usage
from src.guardrails.pii import hash_id


def test_gemini_style_usage():
    raw = {"usage_metadata": {"prompt_token_count": 812, "candidates_token_count": 41}}

    assert token_usage(raw) == (812, 41)


def test_openai_style_usage():
    raw = {
        "usage": {"prompt_tokens": 300, "completion_tokens": 25, "total_tokens": 325}
    }

    assert token_usage(raw) == (300, 25)


def test_usage_given_as_an_object():
    usage = SimpleNamespace(
        model_dump=lambda: {"prompt_token_count": 10, "candidates_token_count": 2}
    )

    assert token_usage({"usage_metadata": usage}) == (10, 2)


def test_missing_usage_counts_as_zero():
    assert token_usage(None) == (0, 0)
    assert token_usage({}) == (0, 0)
    assert token_usage({"usage_metadata": {"prompt_token_count": None}}) == (0, 0)
    assert token_usage("not a dict") == (0, 0)


def test_steps_are_model_plus_tool_calls():
    log = RunLog()
    log.add_llm_call(
        {"usage_metadata": {"prompt_token_count": 100, "candidates_token_count": 10}}
    )
    log.add_tool_call("list_customer_orders")
    log.add_llm_call(
        {"usage_metadata": {"prompt_token_count": 150, "candidates_token_count": 20}}
    )

    assert log.llm_calls == 2
    assert log.tool_calls == ["list_customer_orders"]
    assert log.steps == 3
    assert (log.input_tokens, log.output_tokens) == (250, 30)


def test_run_log_line_has_no_customer_id(caplog):
    log = RunLog()
    log.add_llm_call(
        {"usage_metadata": {"prompt_token_count": 100, "candidates_token_count": 10}}
    )
    log.add_tool_call("get_order_status")
    customer = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"

    with caplog.at_level(logging.INFO, logger="src.agents.run_log"):
        log.write("support", customer)

    assert len(caplog.records) == 1
    line = caplog.records[0].getMessage()
    assert "agent=support" in line
    assert f"customer={hash_id(customer)}" in line
    assert "steps=2 llm_calls=1 tool_calls=1" in line
    assert "tools=get_order_status" in line
    assert "input_tokens=100 output_tokens=10" in line
    assert customer not in line


def test_run_without_a_customer_or_tools(caplog):
    with caplog.at_level(logging.INFO, logger="src.agents.run_log"):
        RunLog().write("ops", None)

    line = caplog.records[0].getMessage()
    assert "customer=-" in line
    assert "tools=-" in line


def test_tool_arguments_kept_not_logged(caplog):
    log = RunLog()
    log.add_tool_call("get_order_status", {"order_ref": "SIP-1"})
    log.add_tool_call("list_customer_orders")

    with caplog.at_level(logging.INFO, logger="src.agents.run_log"):
        log.write("support", None)

    assert log.tool_arguments == [{"order_ref": "SIP-1"}, {}]
    assert "SIP-1" not in caplog.records[0].getMessage()


def test_json_tool_results_are_parsed():
    log = RunLog()
    log.add_tool_result("get_order_status", '{"order": "SIP-1", "status": "delivered"}')
    log.add_tool_result("echo", "plain text")

    assert log.tool_results == [
        ("get_order_status", {"order": "SIP-1", "status": "delivered"}),
        ("echo", "plain text"),
    ]
