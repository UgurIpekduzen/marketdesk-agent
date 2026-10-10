"""Checks that the golden set is well formed. No model and no real data."""

import json

import pytest

from eval.run_eval import GOLDEN_SET, load_golden
from src.knowledge.policy_index import read_sections
from src.orchestrator import Intent
from src.rules.returns import DecisionCode, ReturnReason

EXAMPLES = load_golden()
CUSTOMER_EXAMPLES = [
    example for example in EXAMPLES if example["session"] == "customer"
]
TOOLS = {
    "get_order_status",
    "list_customer_orders",
    "check_return_eligibility",
    "create_return_request",
    "search_policies",
    "escalate_to_human",
    "list_metrics",
    "run_metric",
    "run_sql",
}
CITATIONS = {section.citation for section in read_sections()}


def of_group(group):
    return [example for example in EXAMPLES if example["group"] == group]


def by_id(example):
    return example["id"]


def test_file_is_one_json_object_per_line():
    lines = GOLDEN_SET.read_text(encoding="utf-8").splitlines()

    assert len(lines) == len(EXAMPLES)
    for line in lines:
        assert isinstance(json.loads(line), dict)


def test_set_has_its_examples_in_four_groups():
    assert len(EXAMPLES) == 54
    assert {example["group"] for example in EXAMPLES} == {
        "support",
        "ops",
        "policy",
        "attack",
    }
    # The minimum per group asked for: 8 support, 8 ops, 4 policy, 5 attack.
    assert len(of_group("support")) >= 8
    assert len(of_group("ops")) >= 8
    assert len(of_group("policy")) >= 4
    assert len(of_group("attack")) >= 5


def test_ids_are_unique():
    ids = [example["id"] for example in EXAMPLES]

    assert len(ids) == len(set(ids))


def test_each_group_runs_in_the_session_it_belongs_to():
    for example in of_group("support") + of_group("policy"):
        assert example["session"] == "customer"
    for example in of_group("ops"):
        assert example["session"] == "ops"
    assert {example["session"] for example in of_group("attack")} == {"customer", "ops"}


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_example_has_the_common_fields(example):
    assert example["session"] in ("customer", "ops")
    assert example["question"].strip()
    assert example["note"].strip()
    # An example may accept more than one class when either is harmless.
    intents = example["expected"]["intent"]
    for intent in intents if isinstance(intents, list) else [intents]:
        assert intent in Intent
    for call in example["expected"].get("tools", []):
        assert call["name"] in TOOLS
    for name in example["expected"].get("forbidden_tools", []):
        assert name in TOOLS


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_no_example_holds_a_raw_id(example):
    # Orders are picked by SQL when the run starts; ids are never written down.
    text = json.dumps(example)

    assert not any(
        len(word) == 32 and all(character in "0123456789abcdef" for character in word)
        for word in text.replace('"', " ").replace("'", " ").split()
    )


@pytest.mark.parametrize("example", CUSTOMER_EXAMPLES, ids=by_id)
def test_customer_example_selects_its_customer_with_sql(example):
    sql = example["select_sql"]

    assert sql.lstrip().upper().startswith("SELECT")
    assert ";" not in sql
    # Deterministic: the same row every time.
    assert "ORDER BY" in sql
    assert "LIMIT 1" in sql
    assert ("{order}" in example["question"]) == ("o.order_id" in sql)


@pytest.mark.parametrize("example", of_group("support"), ids=by_id)
def test_support_example_names_valid_codes(example):
    expected = example["expected"]

    # An empty list is a statement too: no tool is to be called.
    assert isinstance(expected["tools"], list)
    if "decision" in expected:
        assert expected["decision"] in DecisionCode
    if "label" in example:
        assert example["label"]["reason"] in ReturnReason
        assert example["label"]["decision"] == expected["decision"]


def test_every_decision_code_of_the_rule_engine_has_an_example():
    covered = {
        example["expected"]["decision"]
        for example in of_group("support")
        if "decision" in example["expected"]
    }

    assert covered == set(DecisionCode)


@pytest.mark.parametrize("example", of_group("ops"), ids=by_id)
def test_ops_example_has_a_golden_select(example):
    sql = example["golden_sql"]

    assert sql.lstrip().upper().startswith("SELECT")
    assert ";" not in sql
    assert isinstance(example["ordered"], bool)
    # An ordered comparison needs an ORDER BY in the golden SQL.
    assert not example["ordered"] or "ORDER BY" in sql
    # Written against the raw tables, not the views the agent uses.
    assert "v_order" not in sql


@pytest.mark.parametrize("example", of_group("policy"), ids=by_id)
def test_policy_example_cites_a_section_that_exists(example):
    sources = example["source"]
    sources = sources if isinstance(sources, list) else [sources]

    assert set(sources) <= CITATIONS
    assert example["reference_answer"].strip()
    assert {"name": "search_policies"} in example["expected"]["tools"]


@pytest.mark.parametrize("example", of_group("attack"), ids=by_id)
def test_attack_example_says_what_must_not_happen(example):
    assert set(example["expected"]) & {
        "refused",
        "forbidden_tools",
        "must_not_match",
        "awaiting_approval",
        "decision_if_called",
    }


def test_setup_statement_only_adds_a_return_request():
    setups = [example["setup_sql"] for example in EXAMPLES if "setup_sql" in example]

    assert setups
    for setup in setups:
        assert setup.startswith("INSERT INTO return_requests ")
        assert ";" not in setup


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_example_with_a_refund_amount_has_a_label(example):
    # The amount is taken from the rule engine's decision for the label;
    # without a label the placeholder would stay in the expected value.
    if "{refund_amount" in json.dumps(example["expected"]):
        assert "label" in example


def test_every_example_is_in_one_split_and_test_covers_every_group():
    assert {example["split"] for example in EXAMPLES} == {"dev", "test"}
    held_out = [example for example in EXAMPLES if example["split"] == "test"]
    assert {example["group"] for example in held_out} == {
        "support",
        "ops",
        "policy",
        "attack",
    }
    # Enough held out for the total to mean something.
    assert len(held_out) >= 25
