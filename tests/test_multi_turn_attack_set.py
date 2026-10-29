"""Tests for the multi-turn attack set: the file itself, without a model.

Attacks that a single message does not try: an approval claimed over
several turns, a slide from one's own order to another customer's, a role
built up turn by turn, a rule planted early and used later, a history the
model never wrote, the instructions pulled out in pieces; and in an
operations session, a slide towards raw tables and an administrator who
asks for ATTACH and PRAGMA.
"""

import json
import re

import pytest

from eval.run_eval import MULTI_TURN_ATTACK_SET, RESULT_PREFIXES, load_golden
from src.agents.support import system_prompt
from src.guardrails.pii import RAW_ID_PATTERN
from src.orchestrator import Intent

EXAMPLES = load_golden(MULTI_TURN_ATTACK_SET)
by_id = lambda example: example["id"]


def said(example: dict) -> list[dict]:
    return [turn for turn in example["turns"] if "say" in turn]


def test_set_has_eight_flows_both_sessions():
    assert [example["id"] for example in EXAMPLES] == [f"A{n}" for n in range(1, 9)]
    assert {example["session"] for example in EXAMPLES} == {"customer", "ops"}
    assert all(len(said(example)) >= 2 for example in EXAMPLES)
    assert {example["attack"] for example in EXAMPLES} == {"LLM01"}


def test_results_have_own_name():
    assert RESULT_PREFIXES["multi_turn_attacks"] == "multi_turn_attacks_v1"


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_every_flow_is_well_formed(example):
    assert example["note"].strip()
    for turn in said(example):
        intents = turn["expected"]["intent"]
        for intent in intents if isinstance(intents, list) else [intents]:
            assert intent in Intent
        for pattern in turn["expected"].get("must_not_match", []):
            re.compile(pattern)
    assert RAW_ID_PATTERN.search(json.dumps(example)) is None
    # An operations session has no approval card to click.
    if example["session"] == "ops":
        assert not any("click" in turn for turn in example["turns"])


def test_forbidden_phrases_are_in_the_prompt():
    # If the instructions changed, the check would look for words they no
    # longer hold.
    leaked = next(e for e in EXAMPLES if e["id"] == "A6")
    phrases = said(leaked)[0]["expected"]["must_not_match"]

    assert all(phrase in system_prompt() for phrase in phrases)
