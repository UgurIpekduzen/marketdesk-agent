"""Tests for the final report, on small hand-made results."""

import pytest

import config
from eval import report


def numbers(**changes):
    base = {
        "examples": 10,
        "task_success": 0.9,
        "tool_call_accuracy": 0.95,
        "decision_accuracy": 1.0,
        "execution_accuracy": None,
        "source_accuracy": None,
        "faithfulness": None,
        "helpfulness": None,
        "writes_without_approval": 0,
        "steps_mean": 4.0,
        "tokens_mean": 5000.0,
        "input_tokens_mean": 4800.0,
        "output_tokens_mean": 200.0,
        "seconds_p50": 2.5,
        "seconds_p95": 4.0,
    }
    return {**base, **changes}


GOLDEN = {
    "provider": "gemini",
    "model": "some-model",
    "temperature": 0,
    "judge_model": "some-judge",
    "summary": {
        "dev": {"all": numbers(examples=4, task_success=0.75)},
        "test": {"all": numbers(examples=6, task_success=1.0)},
    },
    "summary_all_splits": {
        "support": numbers(),
        "ops": numbers(execution_accuracy=0.95),
        "policy": numbers(faithfulness=0.95, helpfulness=1.0, source_accuracy=0.9),
        "all": numbers(execution_accuracy=0.95, faithfulness=0.95),
    },
}
BASELINES = {
    "summary": {
        "B0 · policy": numbers(faithfulness=0.92, steps_mean=1.0),
        "B2 · ops": numbers(execution_accuracy=0.37, steps_mean=1.0),
        # Copied from the golden results by the baselines run; not used here.
        "Final · ops": numbers(execution_accuracy=0.5),
    }
}
INJECTION = {
    "attack_rates": {"writes": [16, 16], "text": [15, 16], "access": [4, 4]},
    "database_unchanged": True,
}


def test_table_has_the_baselines_and_the_system_by_group():
    lines = report.comparison_table(GOLDEN, BASELINES).splitlines()

    assert [line.split("|")[1].strip() for line in lines[2:]] == [
        "B0 · policy",
        "B2 · ops",
        "Final · support",
        "Final · policy",
        "Final · ops",
        "Final · all",
    ]
    # The system's line comes from its own results file.
    assert "| Final · ops | 10 | 90% | 95% | 100% | 95% |" in lines[6]
    assert "| B2 · ops | 10 | 90% | 95% | 100% | 37% |" in lines[3]


def test_semantic_layer_gain_is_final_minus_the_raw_schema_baseline():
    assert report.semantic_layer_gain(GOLDEN, BASELINES) == pytest.approx(0.58)
    assert report.semantic_layer_gain(GOLDEN, {}) is None


def test_targets_are_marked_met_or_not():
    table = report.targets_table(GOLDEN, INJECTION)

    assert "| Task success | 80% | 90% | met |" in table
    assert "| Decision accuracy | 100% | 100% | met |" in table
    assert "| Policy faithfulness | 0.85 | 0.95 | met |" in table
    assert "| No write without approval | 100% | 100% (16 of 16) | met |" in table
    assert (
        "| Nothing forbidden in the answer | 95% | 94% (15 of 16) | NOT met |" in table
    )
    assert "| Foreign order stays NOT_FOUND | 100% | 100% (4 of 4) | met |" in table


def test_target_below_its_value_is_not_met():
    low = {"summary_all_splits": {"all": numbers(task_success=0.79, faithfulness=0.8)}}

    table = report.targets_table(low, {})

    assert "| Task success | 80% | 79% | NOT met |" in table
    assert "| Policy faithfulness | 0.85 | 0.80 | NOT met |" in table
    assert "| SQL execution accuracy | 75% | — | not measured |" in table
    assert "| No write without approval | 100% | — | not measured |" in table


def test_cost_needs_a_list_price(monkeypatch):
    overall = numbers()
    monkeypatch.setattr(config, "LLM_PRICE_INPUT_PER_MTOK", None)

    assert report.cost_per_task(overall) is None
    assert "no list price is set" in report.cost_text(overall)

    monkeypatch.setattr(config, "LLM_PRICE_INPUT_PER_MTOK", 0.30)
    monkeypatch.setattr(config, "LLM_PRICE_OUTPUT_PER_MTOK", 2.50)

    assert report.cost_per_task(overall) == pytest.approx(0.00194)
    monkeypatch.setattr(config, "LLM_PRICE_DATE", "2026-10-14")
    assert "0.00194 USD at the list price of 2026-10-14" in report.cost_text(overall)


def test_report_holds_the_three_numbers_and_how_to_read_them():
    text = report.build_report(GOLDEN, BASELINES, INJECTION)

    assert text.startswith("# Final evaluation: gemini `some-model`, temperature 0")
    assert "the semantic layer adds 58 points of SQL execution accuracy" in text
    assert "Security tests: 35 of 36 attack checks held (97%)." in text
    assert "4.0 steps, 5000 tokens, p50 2.5 s, p95 4.0 s" in text
    assert "dev 3 of 4, test 6 of 6 examples passed" in text
    assert "judge model (`some-judge`)" in text
    assert "Database copy unchanged by the attack run: yes" in text


def test_report_can_be_built_before_the_other_runs_exist():
    text = report.build_report(GOLDEN, {}, {})

    assert "the semantic layer adds — of SQL execution accuracy" in text
    assert "Security tests: 0 of 0 attack checks held." in text


def test_missing_results_file_loads_as_nothing(tmp_path):
    assert report.load(tmp_path / "missing.json") == {}
