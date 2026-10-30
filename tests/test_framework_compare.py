"""Tests for the comparison of two agent frameworks: that the LlamaIndex ways
make the model calls they are set up to make, that the stand-in records
nothing, and what the report says. Pydantic AI is not a dependency of the
project, so the tests that need it are skipped when it is not installed. The
stand-in answers at once: no network, no key."""

import asyncio
from pathlib import Path

import pytest

import config
from eval import framework_compare as compare
from eval.framework_overhead import MODEL_CALLS

ROOT = Path(__file__).resolve().parent.parent


def test_bare_run_makes_the_calls_asked():
    for model_calls in MODEL_CALLS:
        _, _, made = asyncio.run(compare.llama_bare(model_calls))

        assert made == model_calls


def test_wrapped_run_makes_the_calls_asked():
    for model_calls in MODEL_CALLS:
        _, _, made = asyncio.run(compare.llama_wrapped(model_calls))

        assert made == model_calls


def test_light_stand_in_records_nothing():
    agent, context = compare.llama_agent(3)

    async def play():
        await agent.run("hello", ctx=context, max_iterations=config.MAX_STEPS)

    asyncio.run(play())

    assert agent.llm.requests == []
    assert agent.llm.script == []


def test_measure_gives_a_summary():
    result = asyncio.run(compare.measure(compare.llama_bare, 2, runs=3))

    assert result["runs"] == 3
    assert result["model_calls_made"] == [2]
    assert result["run_ms_p50"] > 0


def test_pydantic_run_makes_the_calls_asked():
    pytest.importorskip("pydantic_ai")

    for model_calls in MODEL_CALLS:
        _, _, made = asyncio.run(compare.pydantic_run(model_calls))

        assert made == model_calls


def test_langchain_run_makes_the_calls_asked():
    pytest.importorskip("langchain")

    for model_calls in MODEL_CALLS:
        _, _, made = asyncio.run(compare.langchain_run(model_calls))

        assert made == model_calls


def test_missing_framework_is_left_out():
    names = list(compare.ways())

    assert names[:2] == [
        "LlamaIndex, bare agent.run",
        "LlamaIndex, through run_agent",
    ]
    for package, label in (
        ("pydantic-ai-slim", "Pydantic AI"),
        ("langchain", "LangChain"),
    ):
        listed = any(name.startswith(label) for name in names)
        assert listed == (compare.installed(package) is not None)


def scenario(model_calls):
    return {
        "model_calls": model_calls,
        "run_ms_p50": 8.0,
        "run_ms_p95": 9.0,
        "step_ms_p50": 4.0,
        "step_ms_p95": 4.5,
        "build_ms_p50": 0.6,
    }


def test_report_lists_every_way_and_version():
    result = {
        "runs": 200,
        "ways": {
            "LlamaIndex, bare agent.run": {
                "versions": {"llama-index-core": "0.14.25"},
                "scenarios": [scenario(2)],
            },
            "Pydantic AI 2.63.0": {
                "versions": {"pydantic-ai-slim": "2.63.0"},
                "scenarios": [scenario(2)],
            },
            "LangChain 1.4.7 create_agent (on LangGraph)": {
                "versions": {"langchain": "1.4.7", "langgraph": "1.2.19"},
                "scenarios": [scenario(2)],
            },
        },
        "model": {"examples": 25, "model_calls": 83, "ms_per_call": 800.0},
    }

    text = compare.markdown(result)

    assert "| LlamaIndex, bare agent.run | 2 | 8.0 | 9.0 | 4.0 | 4.5 | 0.6 |" in text
    assert "| Pydantic AI 2.63.0 | 2 |" in text
    assert "| LangChain 1.4.7 create_agent (on LangGraph) | 2 |" in text
    assert (
        "llama-index-core 0.14.25, pydantic-ai-slim 2.63.0, langchain 1.4.7, "
        "langgraph 1.2.19." in text
    )
    assert "800.0 ms per call" in text
    assert "not a better one" in text


def test_other_frameworks_not_dependencies():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    for name in ("pydantic-ai", "langchain", "langgraph"):
        assert name not in pyproject
