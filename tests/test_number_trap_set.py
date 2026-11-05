"""Tests for the number trap set and for what a run records about the critic.

The set asks operations questions that tempt the model to state a number of
its own. Whether the critic catches them is measured by running it with and
without the critic; here the file and the records are checked, no model.
"""

import json

import pytest

from eval import run_eval
from src.orchestrator import Intent

EXAMPLES = run_eval.load_golden(run_eval.NUMBER_TRAP_SET)


def test_set_has_six_derived_questions():
    assert [example["id"] for example in EXAMPLES] == [f"N{n}" for n in range(1, 7)]
    assert {example["session"] for example in EXAMPLES} == {"ops"}
    assert {example["group"] for example in EXAMPLES} == {"ops"}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example["id"])
def test_examples_check_final_answer_numbers(example):
    assert example["note"].strip()
    assert example["expected"]["intent"] in Intent
    assert example["expected"]["numbers_in_tool_output"] is True
    # Asked in the question, not in the data: no raw id.
    assert len(json.dumps(example)) < 400


def test_results_named_for_both_critic_modes():
    assert run_eval.RESULT_PREFIXES["number_traps"] == "number_traps_v1"
    with_critic = run_eval.result_name(run_eval.NUMBER_TRAP_SET, "some/model")
    without = run_eval.result_name(run_eval.NUMBER_TRAP_SET, "some/model", critic=False)

    assert with_critic == "number_traps_v1_some_model"
    assert without == "number_traps_v1_some_model_no-critic"
    second = run_eval.result_name(
        run_eval.NUMBER_TRAP_SET, "some/model", variant="plain"
    )
    assert second == "number_traps_v1_some_model_critic-plain"
    # The wording in use has the plain name.
    in_use = run_eval.config.CRITIC_DEFAULT_VARIANT
    assert (
        run_eval.result_name(run_eval.NUMBER_TRAP_SET, "some/model", variant=in_use)
        == with_critic
    )


class FakeIntent:
    def __init__(self, value):
        self.value = value


class Log:
    def __init__(self, results):
        self.tool_calls, self.tool_arguments = [], []
        self.tool_results = results
        self.llm_calls = self.input_tokens = self.output_tokens = 0


class Reply:
    def __init__(self, text, critic=None):
        self.text = text
        self.critic = critic
        self.log = Log([("run_metric", {"rows": [[29, 29]]})])


class Answer:
    def __init__(self, intent, text, critic=None):
        self.display = text
        self.intent = FakeIntent(intent)
        self.reply = Reply(text, critic)
        self.router_log = Log([])
        self.awaiting_approval = None
        self.refused = False


def scored(intent, text, critic=None):
    example = {
        "id": "N",
        "group": "ops",
        "question": "Kaç sipariş var?",
        "expected": {"intent": intent, "numbers_in_tool_output": True},
    }
    prepared = {"placeholders": {}, "label_ok": True, "requests_before": 0}
    return run_eval.score(example, prepared, Answer(intent, text, critic), 0)


def test_ops_row_records_ungrounded_numbers():
    row = scored("ops_metric", "777 sipariş var.", critic="flagged")

    assert row["ungrounded_numbers"] == ["777"]
    assert row["critic"] == "flagged"
    assert row["success"] is False


def test_tool_numbers_only_is_a_success():
    row = scored("ops_metric", "29 sipariş var.", critic="ok")

    assert row["ungrounded_numbers"] == []
    assert row["success"] is True


def test_other_agent_row_has_no_critic_data():
    row = scored("support", "Siparişiniz yolda.")

    assert "ungrounded_numbers" not in row
    assert "critic" not in row


def test_summary_counts_ungrounded_answers():
    rows = [
        {"ungrounded_numbers": ["777"], "critic": "flagged"},
        {"ungrounded_numbers": [], "critic": "corrected"},
        {"ungrounded_numbers": [], "critic": "ok"},
        {"ungrounded_numbers": [], "critic": None},
    ]

    assert run_eval.count_where(rows, "ungrounded_numbers", bool) == 1
    assert run_eval.count_where(rows, "critic", lambda value: value == "corrected") == 1
    assert run_eval.count_where(rows, "critic", lambda value: value == "flagged") == 1
    # Rows without the field (another agent) are not counted at all.
    assert run_eval.count_where([{"id": 1}], "critic", bool) is None
