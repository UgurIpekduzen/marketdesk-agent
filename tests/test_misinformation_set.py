"""Tests for the misinformation set: the file itself, without a model.

The set tries to make the system state wrong things with confidence: false
premises, topics and sections the policies do not have, metrics and periods
the data does not hold, causal traps and pressure to guess. Its checks are
code where code can tell (grounding checks in eval/scoring.py) and the
judge for the rest.
"""

import json
import re

import pytest

from eval.run_eval import MISINFORMATION_SET, RESULT_PREFIXES, load_golden
from src.guardrails.pii import RAW_ID_PATTERN
from src.knowledge.policy_index import read_sections
from src.orchestrator import Intent

EXAMPLES = load_golden(MISINFORMATION_SET)
by_id = lambda example: example["id"]
CUSTOMER = [example for example in EXAMPLES if example["session"] == "customer"]
OPS = [example for example in EXAMPLES if example["session"] == "ops"]


def test_set_has_twelve_scenarios():
    assert len(EXAMPLES) == 14
    assert len({example["id"] for example in EXAMPLES}) == 14
    assert {example["split"] for example in EXAMPLES} == {"dev"}
    assert {example["attack"] for example in EXAMPLES} == {"LLM09"}
    assert len(CUSTOMER) == 7
    assert len(OPS) == 7


def test_results_have_own_name():
    assert RESULT_PREFIXES["misinformation_tests"] == "misinformation_v1"


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_every_example_is_well_formed(example):
    expected = example["expected"]

    assert example["note"].strip()
    assert expected["intent"] in Intent
    for pattern in expected.get("must_not_match", []):
        re.compile(pattern)
    assert expected["no_future_date"] is True
    assert RAW_ID_PATTERN.search(json.dumps(example)) is None


@pytest.mark.parametrize("example", CUSTOMER, ids=by_id)
def test_customer_example_checks_citations(example):
    sql = example["select_sql"]

    assert example["expected"]["citations_returned"] is True
    assert sql.lstrip().upper().startswith("SELECT")
    assert ";" not in sql
    assert "LIMIT 1" in sql


@pytest.mark.parametrize("example", OPS, ids=by_id)
def test_an_ops_example_checks_its_numbers(example):
    assert example["expected"]["numbers_in_tool_output"] is True
    assert example["group"] == "ops"


@pytest.mark.parametrize("example", [e for e in EXAMPLES if "source" in e], ids=by_id)
def test_a_source_names_a_real_section(example):
    citations = {section.citation for section in read_sections()}

    assert example["source"] in citations


def test_asked_sections_do_not_exist():
    # M6 asks for a ninth section of the returns policy, M7 for a policy
    # document there is none of.
    sections = read_sections()
    returns = [s for s in sections if s.document == "İade Politikası"]

    assert len(returns) < 9
    assert not any("Sadakat" in s.document for s in sections)
