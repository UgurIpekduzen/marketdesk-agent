"""Tests for the framework overhead measurement: that a run makes the model
calls it was set up to make, that the figures are worked out right, and what
the report says. The stand-in model answers at once: no network, no key."""

import asyncio
import json

import pytest

import config
from eval import framework_overhead as overhead


def test_run_makes_the_model_calls_asked():
    for model_calls in overhead.MODEL_CALLS:
        _, _, made = asyncio.run(overhead.one_run(model_calls))

        assert made == model_calls


def test_longest_run_fits_the_step_limit():
    assert max(overhead.MODEL_CALLS) == config.MAX_STEPS


def test_measure_reports_every_run():
    result = asyncio.run(overhead.measure(2, runs=3))

    assert result["runs"] == 3
    assert result["model_calls_made"] == [2]
    assert result["run_ms_p50"] > 0
    assert result["step_ms_p50"] == pytest.approx(result["run_ms_p50"] / 2, abs=0.01)


def test_summary_works_out_percentiles():
    took = [10.0, 20.0, 30.0, 40.0]

    result = overhead.summarize(4, [1.0] * 4, took, {4})

    assert result["run_ms_p50"] == 25.0
    assert result["run_ms_max"] == 40.0
    assert result["step_ms_p50"] == 6.25


def row(split, seconds, llm_calls):
    return {"split": split, "seconds": seconds, "llm_calls": llm_calls}


def test_model_time_uses_dev_rows_only(tmp_path):
    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps(
            {
                "examples": [
                    row("dev", 2.0, 2),
                    row("dev", 1.0, 2),
                    row("test", 90.0, 1),
                    row("dev", 5.0, 0),
                ]
            }
        ),
        encoding="utf-8",
    )

    found = overhead.model_time_per_call(path)

    assert found == {"examples": 2, "model_calls": 4, "ms_per_call": 750.0}


def test_model_time_is_none_without_results(tmp_path):
    assert overhead.model_time_per_call(tmp_path / "missing.json") is None


def scenario(model_calls):
    return {
        "model_calls": model_calls,
        "run_ms_p50": 8.0,
        "run_ms_p95": 9.0,
        "run_ms_max": 10.0,
        "step_ms_p50": 4.0,
        "step_ms_p95": 4.5,
        "build_ms_p50": 0.6,
    }


def test_report_compares_with_the_model():
    result = {
        "runs": 200,
        "scenarios": [scenario(2), scenario(8)],
        "model": {"examples": 25, "model_calls": 83, "ms_per_call": 800.0},
    }

    text = overhead.markdown(result)

    assert "| 8 | 8.0 | 9.0 | 10.0 | 4.0 | 4.5 | 0.6 |" in text
    assert "800.0 ms per call in the 25 development examples" in text
    assert "0.50%" in text
    assert "upper bound" in text


def test_report_says_when_nothing_to_compare():
    result = {"runs": 10, "scenarios": [scenario(1)], "model": None}

    assert "No model time to compare with" in overhead.markdown(result)
