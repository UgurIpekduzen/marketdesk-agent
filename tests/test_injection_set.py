"""Tests for the attack set: the file itself, without running a model."""

import json
import re

import pytest

from eval.run_eval import INJECTION_SET, load_golden
from src.guardrails.pii import RAW_ID_PATTERN
from src.knowledge import safe_views
from src.orchestrator import Intent

EXAMPLES = load_golden(INJECTION_SET)
by_id = lambda example: example["id"]


def test_every_attack_of_the_list_has_an_example():
    assert {example["attack"] for example in EXAMPLES} == {
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
    }
    assert len(EXAMPLES) == 16
    assert len({example["id"] for example in EXAMPLES}) == 16


def test_all_are_attack_examples_shown_one_by_one():
    # Not held out: a failed attack has to be looked at.
    assert {example["group"] for example in EXAMPLES} == {"attack"}
    assert {example["split"] for example in EXAMPLES} == {"dev"}
    assert {example["session"] for example in EXAMPLES} == {"customer", "ops"}


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_example_says_what_must_not_happen(example):
    expected = example["expected"]

    assert example["note"].strip()
    intents = expected["intent"]
    for intent in intents if isinstance(intents, list) else [intents]:
        assert intent in Intent
    assert set(expected) & {
        "refused",
        "forbidden_tools",
        "must_not_match",
        "awaiting_approval",
        "decision_if_called",
    }
    for pattern in expected.get("must_not_match", []):
        re.compile(pattern)


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_no_example_holds_a_raw_id(example):
    assert RAW_ID_PATTERN.search(json.dumps(example)) is None


@pytest.mark.parametrize(
    "example", [e for e in EXAMPLES if e["session"] == "customer"], ids=by_id
)
def test_customer_example_selects_its_customer_with_sql(example):
    sql = example["select_sql"]

    assert sql.lstrip().upper().startswith("SELECT")
    assert ";" not in sql
    assert "ORDER BY" in sql
    assert "LIMIT 1" in sql


def test_nothing_is_added_to_the_database_for_the_set():
    # Zero synthetic rows: no example sets a stage.
    assert [example["id"] for example in EXAMPLES if "setup_sql" in example] == []


def test_review_text_reaches_no_model_in_this_version():
    # Why A5 and A6 are tried through the message instead of stored
    # reviews: the views the agents may read hold scores and dates of
    # reviews, never their text.
    definitions = " ".join(safe_views.SAFE_VIEWS.values()).lower()

    assert "review_score" in definitions
    assert "review_comment" not in definitions
