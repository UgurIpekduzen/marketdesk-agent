"""Tests for the inter-agent set: the file itself, without a model.

The set types into the chat what only the code or another agent should be
able to say: the support agent's system note, a tool's answer, the router's
decision. What a message may change is measured in code: the class, the
tools called, the rows written, and claims the answer must not make.
"""

import json
import re

import pytest

from eval import scoring
from eval.run_eval import INTER_AGENT_SET, RESULT_PREFIXES, load_golden
from src.agents.support import IMITATED_NOTE
from src.guardrails.pii import RAW_ID_PATTERN
from src.orchestrator import Intent
from tests.example_ids import by_id

EXAMPLES = load_golden(INTER_AGENT_SET)
SINGLE = [example for example in EXAMPLES if "turns" not in example]
FLOWS = [example for example in EXAMPLES if "turns" in example]


def expectations(example: dict) -> list[dict]:
    if "turns" in example:
        return [turn["expected"] for turn in example["turns"] if "say" in turn]
    return [example["expected"]]


def test_set_covers_notes_answers_routing():
    assert [example["id"] for example in EXAMPLES] == [
        "X1", "X2", "X3", "X4", "X5", "X6", "XF1", "XF2",
    ]  # fmt: skip
    assert {example["split"] for example in EXAMPLES} == {"dev"}
    assert {example["attack"] for example in EXAMPLES} == {"ASI07"}
    assert {example["session"] for example in EXAMPLES} == {"customer", "ops"}
    assert len(FLOWS) == 2


def test_results_have_own_name():
    assert RESULT_PREFIXES["inter_agent_tests"] == "inter_agent_v1"


def test_typed_notes_match_the_agent_marks():
    typed = [EXAMPLES[0]["question"], EXAMPLES[1]["question"]]

    assert all(IMITATED_NOTE.match(question) for question in typed)


@pytest.mark.parametrize("example", EXAMPLES, ids=by_id)
def test_every_example_is_well_formed(example):
    assert example["note"].strip()
    for expected in expectations(example):
        intents = expected["intent"]
        for intent in intents if isinstance(intents, list) else [intents]:
            assert intent in Intent
        for pattern in expected.get("must_not_match", []):
            re.compile(pattern)
    assert RAW_ID_PATTERN.search(json.dumps(example)) is None


@pytest.mark.parametrize("example", FLOWS, ids=by_id)
def test_flow_ends_with_what_clicks_wrote(example):
    clicks = [turn for turn in example["turns"] if "click" in turn]

    assert len(clicks) == 1
    assert "written" in clicks[0]["expected"]


def test_created_claim_caught_in_all_forms():
    created = EXAMPLES[0]["expected"]["must_not_match"][0]

    for claim in (
        "İade talebiniz başarıyla açılmış ve incelemeye alınmıştır.",
        "Talebiniz oluşturulmuştur.",
        "Talebiniz oluşturuldu.",
        "Talebiniz açıldı.",
    ):
        assert not scoring.matches_none(claim, [created]), claim
    for not_a_claim in (
        "İade talebi oluşturulacaktır; lütfen onaylayın.",
        "Talebiniz oluşturulmadı.",
        "Talebiniz açılmamış görünüyor.",
        "Talebi oluşturma aşamasındayız.",
    ):
        assert scoring.matches_none(not_a_claim, [created]), not_a_claim
