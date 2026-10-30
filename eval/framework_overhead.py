"""How much time does the agent framework itself add to a step?

Usage:  python eval/framework_overhead.py [--runs N]

A task spends its time waiting for the model. What the framework (LlamaIndex's
FunctionAgent workflow) adds around each model call is measured here with the
model taken out: a stand-in model (tests/fakes.py) answers at once, so the
time of a run is the framework's, plus the project's own run_agent around it
(event stream, run log) and the stand-in's bookkeeping (it records every
request it receives). The figure is therefore an upper bound for the framework.

A run asks for a number of tools one after the other and then answers, so a
run of n model calls has n - 1 tool calls. The tool does nothing. What is
reported is the time of a whole run and the time of a step (a run divided by
its model calls). The time to build the agent and its context, done once per
session, is reported apart.

For scale, the model's own time per call is taken from the development
examples of the golden set run (eval/results), if the file is there: the
seconds the model took, divided by its calls. The framework's time is not
compared with another framework: only this one is measured.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

import config
from eval.terminal_table import terminal_tables
from src.agents.runner import run_agent
from tests.fakes import FakeLLM

RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
GOLDEN_RESULTS = RESULTS_DIR / "golden_v1_gemini-3.5-flash-lite.json"
# Model calls in a run: an answer alone, and then one to seven tools first.
# Eight is the step limit.
MODEL_CALLS = (1, 2, 4, config.MAX_STEPS)
WARM_UP_RUNS = 5
DEFAULT_RUNS = 200


async def lookup(item: str) -> str:
    """Look an item up."""
    return f"found {item}"


def agent_and_context(model_calls: int) -> tuple[FunctionAgent, Context]:
    """An agent whose stand-in model asks for a tool in all calls but the last."""
    script = [[("lookup", {"item": str(number)})] for number in range(model_calls - 1)]
    agent = FunctionAgent(
        name="overhead",
        tools=[FunctionTool.from_defaults(async_fn=lookup)],
        llm=FakeLLM(script=[*script, "done"]),
        system_prompt="Answer briefly.",
    )
    return agent, Context(agent)


def milliseconds_since(start: float) -> float:
    return (time.perf_counter() - start) * 1000


async def one_run(model_calls: int) -> tuple[float, float, int]:
    """(build ms, run ms, model calls made)."""
    start = time.perf_counter()
    agent, context = agent_and_context(model_calls)
    built = milliseconds_since(start)
    start = time.perf_counter()
    _, log = await run_agent(agent, context, "hello")
    return built, milliseconds_since(start), log.llm_calls


async def measure(model_calls: int, runs: int) -> dict:
    for _ in range(WARM_UP_RUNS):
        await one_run(model_calls)
    built, took, made = [], [], set()
    for _ in range(runs):
        build_ms, run_ms, calls = await one_run(model_calls)
        built.append(build_ms)
        took.append(run_ms)
        made.add(calls)
    return summarize(model_calls, built, took, made)


def percentile(values: list[float], share: float) -> float:
    return float(np.percentile(values, share))


def summarize(model_calls: int, built: list, took: list, made: set) -> dict:
    return {
        "model_calls": model_calls,
        "runs": len(took),
        # What the stand-in model was asked for must be what the run made.
        "model_calls_made": sorted(made),
        "build_ms_p50": round(percentile(built, 50), 2),
        "run_ms_p50": round(percentile(took, 50), 2),
        "run_ms_p95": round(percentile(took, 95), 2),
        "run_ms_max": round(max(took), 2),
        "step_ms_p50": round(percentile(took, 50) / model_calls, 2),
        "step_ms_p95": round(percentile(took, 95) / model_calls, 2),
    }


def model_time_per_call(path: Path = GOLDEN_RESULTS) -> dict | None:
    """The model's seconds per call, from the development examples of a run."""
    if not path.exists():
        return None
    rows = [
        row
        for row in json.loads(path.read_text(encoding="utf-8"))["examples"]
        if row["split"] == "dev" and row["llm_calls"]
    ]
    if not rows:
        return None
    seconds = sum(row["seconds"] for row in rows)
    calls = sum(row["llm_calls"] for row in rows)
    return {
        "examples": len(rows),
        "model_calls": calls,
        "ms_per_call": round(seconds * 1000 / calls, 1),
    }


# --- Report -----------------------------------------------------------------------


def markdown(result: dict) -> str:
    lines = [
        "# Framework overhead: LlamaIndex FunctionAgent without the model",
        "",
        (
            f"{result['runs']} runs per row after {WARM_UP_RUNS} warm-up runs, CPU, a "
            "stand-in model that answers at once and a tool that does nothing. The "
            "time is the framework's plus the project's own run_agent around it, "
            "and the stand-in's own bookkeeping (it records every request), so it "
            "is an upper bound for the framework."
        ),
        "",
        (
            "| Model calls in a run | Run p50 (ms) | Run p95 (ms) | Run max (ms) "
            "| Step p50 (ms) | Step p95 (ms) | Build p50 (ms) |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    for row in result["scenarios"]:
        lines.append(
            f"| {row['model_calls']} | {row['run_ms_p50']} | {row['run_ms_p95']} "
            f"| {row['run_ms_max']} | {row['step_ms_p50']} | {row['step_ms_p95']} "
            f"| {row['build_ms_p50']} |"
        )
    model = result["model"]
    lines.append("")
    if model:
        step = result["scenarios"][-1]["step_ms_p50"]
        lines.append(
            f"For scale: the model took {model['ms_per_call']} ms per call in the "
            f"{model['examples']} development examples of the golden set "
            f"({model['model_calls']} calls). The framework's step above is "
            f"{step / model['ms_per_call'] * 100:.2f}% of that."
        )
    else:
        lines.append(
            "No model time to compare with: the golden set results are missing."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="runs per row")
    args = parser.parse_args()

    scenarios = []
    for model_calls in MODEL_CALLS:
        print(f"measuring {model_calls} model calls ...", flush=True)
        scenarios.append(asyncio.run(measure(model_calls, args.runs)))
    result = {
        "runs": args.runs,
        "scenarios": scenarios,
        "model": model_time_per_call(),
    }
    print(f"\n{terminal_tables(markdown(result))}")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "framework_overhead_v1.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (RESULTS_DIR / "framework_overhead_v1.md").write_text(
        markdown(result), encoding="utf-8"
    )
    print("Results written to eval/results/framework_overhead_v1.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
