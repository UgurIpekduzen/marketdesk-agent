"""Tests for the client layer attack set: the file itself, without a model.

The set asks the real model to write HTML, links and images into its
answers. Whether the page draws such text harmlessly is shown by the view
and page tests and by the browser measurement in the security review; the
set measures whether the model writes it at all.
"""

import json
import re

import pytest

from eval.run_eval import CLIENT_LAYER_SET, RESULT_PREFIXES, load_golden
from src.guardrails.pii import RAW_ID_PATTERN
from src.orchestrator import Intent

EXAMPLES = load_golden(CLIENT_LAYER_SET)
by_id = lambda example: example["id"]


def test_set_covers_both_sessions():
    assert len(EXAMPLES) == 8
    assert len({example["id"] for example in EXAMPLES}) == 8
    assert {example["group"] for example in EXAMPLES} == {"attack"}
    assert {example["split"] for example in EXAMPLES} == {"dev"}
    assert {example["session"] for example in EXAMPLES} == {"customer", "ops"}


def test_results_have_own_name():
    assert RESULT_PREFIXES["client_layer_tests"] == "client_layer_v1"


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_examples_forbid_markup_in_answer(example):
    expected = example["expected"]
    patterns = expected["must_not_match"]

    assert example["note"].strip()
    intents = expected["intent"]
    for intent in intents if isinstance(intents, list) else [intents]:
        assert intent in Intent
    for pattern in patterns:
        re.compile(pattern)
    for form in ("<script", "javascript:", "\\]\\(", "!\\["):
        assert form in patterns, (example["id"], form)


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_no_example_holds_a_raw_id(example):
    assert RAW_ID_PATTERN.search(json.dumps(example)) is None


@pytest.mark.parametrize(
    "example", [e for e in EXAMPLES if e["session"] == "customer"], ids=by_id
)
def test_customer_example_picks_by_sql(example):
    sql = example["select_sql"]

    assert sql.lstrip().upper().startswith("SELECT")
    assert ";" not in sql
    assert "LIMIT 1" in sql
    assert "create_return_request" in example["expected"]["forbidden_tools"]
