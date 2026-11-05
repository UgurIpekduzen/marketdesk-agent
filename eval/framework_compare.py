"""LlamaIndex and Pydantic AI, side by side: what each adds to a step.

Usage:  task eval:overhead:compare            (or, by hand:
        uv run --with pydantic-ai-slim==2.63.0 --with langchain==1.4.7 \\
            python -m eval.framework_compare)

Pydantic AI and LangChain (with LangGraph under it) are not dependencies of
the project. The task adds them for this run only, in a temporary layer, and
pyproject.toml and uv.lock stay as they are. A framework that is not installed
is left out of the table.

The same scenario as eval/framework_overhead.py, in one process: a scripted
model that answers at once, one tool that does nothing, a run of n model calls
asks for a tool n - 1 times and then answers. Three ways are measured:
LlamaIndex's FunctionAgent run bare (agent.run), the same through the
project's own run_agent, a Pydantic AI Agent with its FunctionModel, and an
agent of LangChain's create_agent, which runs on LangGraph (LangGraph's own
create_react_agent is deprecated in favour of it). The scripted model of
LlamaIndex here records nothing (the one of eval/framework_overhead.py records
every request); the scripted LangChain model answers in its async path
directly, as a model reached over the network would.

What this says: the time each framework adds around a model call, in this one
scenario, on the CPU. What it does not say: anything about quality, features,
memory, tracing, or how either behaves with a real model and real tools. The
two frameworks do different work around a step (LlamaIndex runs an event
workflow with a serializable context), so a faster step is not a better one.
"""

import argparse
import asyncio
import importlib.metadata
import json
import sys
import time
from pathlib import Path

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    MessageRole,
    TextBlock,
    ToolCallBlock,
)
from llama_index.core.tools import FunctionTool
from llama_index.core.workflow import Context

import config
from eval.framework_overhead import (
    DEFAULT_RUNS,
    MODEL_CALLS,
    WARM_UP_RUNS,
    milliseconds_since,
    model_time_per_call,
    summarize,
)
from eval.terminal_table import terminal_tables
from src.agents.runner import run_agent
from tests.fakes import FakeLLM

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RESULTS_DIR = PROJECT_ROOT / "eval" / "results"


# --- LlamaIndex -------------------------------------------------------------------


async def lookup(item: str) -> str:
    """Look an item up."""
    return f"found {item}"


class LightLLM(FakeLLM):
    """FakeLLM without its bookkeeping: it plays the script and records nothing."""

    def _answer(self, messages, **kwargs):
        step = self.script.pop(0) if self.script else "(end of script)"
        if isinstance(step, str):
            blocks = [TextBlock(text=step)]
        else:
            blocks = [
                ToolCallBlock(
                    tool_call_id=f"call-{n}", tool_name=name, tool_kwargs=args
                )
                for n, (name, args) in enumerate(step)
            ]
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, blocks=blocks)
        )


def llama_agent(model_calls: int) -> tuple[FunctionAgent, Context]:
    """A LlamaIndex agent whose scripted model makes the given number of calls."""
    script = [[("lookup", {"item": str(n)})] for n in range(model_calls - 1)]
    agent = FunctionAgent(
        name="overhead",
        tools=[FunctionTool.from_defaults(async_fn=lookup)],
        llm=LightLLM(script=[*script, "done"]),
        system_prompt="Answer briefly.",
    )
    return agent, Context(agent)


async def llama_bare(model_calls: int) -> tuple[float, float, int]:
    """One run of the LlamaIndex agent without the project's wrappers."""
    start = time.perf_counter()
    agent, context = llama_agent(model_calls)
    built = milliseconds_since(start)
    start = time.perf_counter()
    await agent.run("hello", ctx=context, max_iterations=config.MAX_STEPS)
    took = milliseconds_since(start)
    # The stand-in plays one script entry per call.
    return built, took, model_calls - len(agent.llm.script)


async def llama_wrapped(model_calls: int) -> tuple[float, float, int]:
    """One run of the LlamaIndex agent with the project's wrappers."""
    start = time.perf_counter()
    agent, context = llama_agent(model_calls)
    built = milliseconds_since(start)
    start = time.perf_counter()
    _, log = await run_agent(agent, context, "hello")
    return built, milliseconds_since(start), log.llm_calls


# --- Measuring ----------------------------------------------------------------------


async def measure(one_run, model_calls: int, runs: int) -> dict:
    """Repeat a run after a warm-up and collect the timings."""
    for _ in range(WARM_UP_RUNS):
        await one_run(model_calls)
    built, took, made = [], [], set()
    for _ in range(runs):
        build_ms, run_ms, calls = await one_run(model_calls)
        built.append(build_ms)
        took.append(run_ms)
        made.add(calls)
    return summarize(model_calls, built, took, made, 0)


def installed(package: str) -> str | None:
    """The installed version of a package, or None."""
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def ways() -> dict:
    """The ways to measure: a runner and the packages whose versions to record."""
    found = {
        "LlamaIndex, bare agent.run": (llama_bare, ["llama-index-core"]),
        "LlamaIndex, through run_agent": (llama_wrapped, ["llama-index-core"]),
    }
    # The two modules import their framework when they are loaded, so they are
    # loaded only when it is installed.
    if version := installed("pydantic-ai-slim"):
        runner = importlib.import_module("eval.framework_pydantic").pydantic_run
        found[f"Pydantic AI {version}"] = (runner, ["pydantic-ai-slim"])
    if version := installed("langchain"):
        runner = importlib.import_module("eval.framework_langchain").langchain_run
        found[f"LangChain {version} create_agent (on LangGraph)"] = (
            runner,
            ["langchain", "langgraph", "langchain-core"],
        )
    return found


def run_all(runs: int) -> dict:
    """Measure every framework for every number of model calls."""
    results = {}
    for name, (one_run, packages) in ways().items():
        rows = []
        for model_calls in MODEL_CALLS:
            print(f"measuring {name}, {model_calls} model calls ...", flush=True)
            rows.append(asyncio.run(measure(one_run, model_calls, runs)))
        results[name] = {
            "versions": {package: installed(package) for package in packages},
            "scenarios": rows,
        }
    return {"runs": runs, "ways": results, "model": model_time_per_call()}


# --- Report -------------------------------------------------------------------------


def markdown(result: dict) -> str:
    """The results as a markdown report."""
    lines = [
        "# Framework overhead: LlamaIndex and Pydantic AI without the model",
        "",
        (
            f"{result['runs']} runs per row after {WARM_UP_RUNS} warm-up runs, CPU, "
            "one process. A scripted model that answers at once and a tool that does "
            "nothing; a run of n model calls asks for the tool n - 1 times and then "
            "answers. One scenario: it says nothing about quality, features, memory or "
            "tracing, and a faster step is not a better one."
        ),
        "",
        (
            "| Way | Model calls | Run p50 (ms) | Run p95 (ms) "
            "| Step p50 (ms) | Step p95 (ms) | Build p50 (ms) |"
        ),
        "|---|---|---|---|---|---|---|",
    ]
    for name, way in result["ways"].items():
        for row in way["scenarios"]:
            lines.append(
                f"| {name} | {row['model_calls']} | {row['run_ms_p50']} "
                f"| {row['run_ms_p95']} | {row['step_ms_p50']} | {row['step_ms_p95']} "
                f"| {row['build_ms_p50']} |"
            )
    versions = dict.fromkeys(
        f"{package} {version}"
        for way in result["ways"].values()
        for package, version in way["versions"].items()
    )
    lines += ["", "Versions: " + ", ".join(versions) + ".", ""]
    model = result["model"]
    if model:
        lines.append(
            f"For scale: the model took {model['ms_per_call']} ms per call in the "
            f"{model['examples']} development examples of the golden set "
            f"({model['model_calls']} calls)."
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    """Run the command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="runs per row")
    args = parser.parse_args()

    result = run_all(args.runs)
    print(f"\n{terminal_tables(markdown(result))}")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "framework_compare_v1.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (RESULTS_DIR / "framework_compare_v1.md").write_text(
        markdown(result), encoding="utf-8"
    )
    print("Results written to eval/results/framework_compare_v1.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
