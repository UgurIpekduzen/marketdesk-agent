"""Tests for the final report, on small hand-made results."""

from pathlib import Path

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


def test_report_says_how_far_the_hand_check_agreed_with_the_judge():
    check = {"lines": 30, "checked": 12, "agreed": 11, "rate": 11 / 12}

    text = report.build_report(GOLDEN, BASELINES, INJECTION, check)

    assert "checked 12 of the judge's scores by hand and agreed with 11 (92%)" in text


def test_report_says_when_the_judge_was_not_checked_by_hand():
    text = report.build_report(GOLDEN, BASELINES, INJECTION)

    assert "have not been checked by hand yet" in text


def test_missing_results_file_loads_as_nothing(tmp_path):
    assert report.load(tmp_path / "missing.json") == {}


GOLDEN_EN = {
    **GOLDEN,
    "language": "en",
    "summary": {
        "dev": {"all": numbers(examples=4, task_success=0.5)},
        "test": {"all": numbers(examples=6, task_success=0.5)},
    },
    "summary_all_splits": {
        "support": numbers(task_success=0.8),
        "policy": numbers(task_success=0.7, faithfulness=0.81, source_accuracy=0.6),
        "all": numbers(task_success=0.75),
    },
}
INJECTION_EN = {
    "attack_rates": {"writes": [16, 16], "text": [14, 16], "access": [4, 4]},
    "summary_all_splits": {"all": numbers(examples=16)},
}


def test_english_results_are_shown_next_to_the_turkish_ones():
    text = report.build_report(
        GOLDEN, BASELINES, INJECTION, golden_en=GOLDEN_EN, injection_en=INJECTION_EN
    )

    section = text[text.index("## English") :]
    assert "| support | 10 | 90% | 80% |" in section
    # Faithfulness TR then EN, as scores.
    assert "| 0.95 | 0.81 |" in section
    assert "The same 10 examples and 16 attacks" in section
    assert "dev 2 of 4, test 3 of 6" in section
    assert "34 of 36 held (94%)" in section
    assert "not checked by hand" in section
    # A group the English run does not have is left out.
    assert "| ops |" not in section


def test_report_has_no_english_section_without_its_results():
    assert "## English" not in report.build_report(GOLDEN, BASELINES, INJECTION)


# --- The attack sets of the red teaming ----------------------------------------

ATTACK_SET_RESULTS = {
    "Indirect injection": {
        "summary_all_splits": {
            "all": numbers(examples=8, task_success=1.0, writes_without_approval=0)
        }
    },
    "Inter-agent messages": {
        "summary_all_splits": {
            "all": numbers(examples=8, task_success=0.875, writes_without_approval=0)
        }
    },
}


def test_the_security_line_adds_up_the_sets_of_the_red_teaming():
    text = report.build_report(
        GOLDEN, BASELINES, INJECTION, attack_sets=ATTACK_SET_RESULTS
    )

    # The attack set's own line is unchanged, the other sets follow it.
    assert "Security tests: 35 of 36 attack checks held (97%)." in text
    assert (
        "2 more sets of the red teaming: 15 of 16 examples passed, "
        "0 return requests written without approval."
    ) in text


def test_the_report_lists_each_attack_set_and_the_total():
    text = report.build_report(
        GOLDEN, BASELINES, INJECTION, attack_sets=ATTACK_SET_RESULTS
    )

    section = text[text.index("## Attack sets") :]
    assert "| Indirect injection | 8 | 8 | 0 |" in section
    assert "| Inter-agent messages | 8 | 7 | 0 |" in section
    assert "| **All** | 16 | 15 | 0 |" in section


def test_a_set_that_was_not_run_is_left_out_of_the_report():
    text = report.build_report(GOLDEN, BASELINES, INJECTION, attack_sets={})

    assert "## Attack sets" not in text
    assert "more sets of the red teaming" not in text


def test_a_set_that_wrote_a_request_shows_it_in_the_total():
    text = report.build_report(
        GOLDEN,
        BASELINES,
        INJECTION,
        attack_sets={
            "Inter-agent messages": {
                "summary_all_splits": {
                    "all": numbers(
                        examples=8, task_success=1.0, writes_without_approval=1
                    )
                }
            }
        },
    )

    assert (
        "1 more set of the red teaming: 8 of 8 examples passed, 1 return request "
        "written without approval."
    ) in text
    assert "| **All** | 8 | 8 | 1 |" in text


def test_the_full_evaluation_runs_every_set_the_report_adds_up():
    taskfile = (Path(__file__).resolve().parent.parent / "Taskfile.yml").read_text(
        encoding="utf-8"
    )
    commands = taskfile.split("  eval:all:")[1].split("\n  eval:multi:")[0]

    # Every set the report reads, English ones included.
    for path in (
        report.GOLDEN_SET,
        report.INJECTION_SET,
        report.GOLDEN_SET_EN,
        report.INJECTION_SET_EN,
        report.MULTI_TURN_SET,
        *report.ATTACK_SETS,
    ):
        wanted = f"--golden eval/{path.name}"
        assert wanted in commands or path == report.GOLDEN_SET, path.name
    # Each set of the critic comparison also runs without the critic and with
    # the second wording of the correction.
    for path in report.CRITIC_SETS:
        for option in ("--no-critic", "--critic-variant plain"):
            lines = [
                line
                for line in commands.splitlines()
                if option in line
                and (f"--golden eval/{path.name}" in line or path == report.GOLDEN_SET)
            ]
            assert lines, (path.name, option)


def test_the_full_evaluation_passes_its_arguments_to_every_run():
    taskfile = (Path(__file__).resolve().parent.parent / "Taskfile.yml").read_text(
        encoding="utf-8"
    )
    commands = taskfile.split("  eval:all:")[1].split("\n  eval:multi:")[0]

    runs = [line for line in commands.splitlines() if "uv run python eval/" in line]
    # Every run takes `-- --paid`; the report calls no model and takes nothing.
    for line in runs:
        assert ("report.py" in line) or ("{{.CLI_ARGS}}" in line), line


# --- The critic of the operations agent -----------------------------------------


def critic_result(**changes):
    counts = {
        "examples": 6,
        "task_success": 0.5,
        "ungrounded_answers": 3,
        "critic_corrected": 0,
        "critic_flagged": 0,
        **changes,
    }
    return {"summary_all_splits": {"ops": numbers(**counts)}}


def test_the_critic_is_shown_with_and_without_for_each_set():
    runs = {
        "Number traps": [
            (
                "on",
                critic_result(
                    ungrounded_answers=1, critic_corrected=2, critic_flagged=1
                ),
            ),
            ("on, plain", critic_result(ungrounded_answers=0, critic_corrected=3)),
            ("off", critic_result()),
        ]
    }

    text = report.build_report(GOLDEN, BASELINES, INJECTION, critic_runs=runs)

    section = text[text.index("## The critic of the operations agent") :]
    assert "| Number traps | on | 6 | 50% | 1 | 2 | 1 |" in section
    assert "| Number traps | on, plain | 6 | 50% | 0 | 3 | 0 |" in section
    assert "| Number traps | off | 6 | 50% | 3 | 0 | 0 |" in section
    assert "wrong thing are not seen by it" in section


def test_no_critic_section_without_both_runs():
    assert "The critic of the operations agent" not in report.build_report(
        GOLDEN, BASELINES, INJECTION
    )
    assert "The critic of the operations agent" not in report.build_report(
        GOLDEN, BASELINES, INJECTION, critic_runs={}
    )
