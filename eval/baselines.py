"""Run three simple baselines on the golden set, to compare the system with.

Usage:  python eval/baselines.py [--db data/marketdesk.db] [--only P1,O2]
                                 [--pause 12] [--no-cache] [--show-test]
                                 [--judge]

Each baseline is one model call per example, with no tools:

- B0: the question and the full text of the policy documents. Run on the
  support and policy examples. It cannot see any order, so whatever it
  states about one is made up; that is what is counted.
- B1: naive retrieval. The question and the five closest policy sections.
  Run on the policy examples.
- B2: SQL from the raw schema. The question and the CREATE TABLE statements
  of the raw tables, without the semantic layer. Run on the ops examples.
  The SQL is run here, read-only, and its rows are compared with the rows
  of the golden query; the rows are never sent to a model.

No order or customer id reaches the provider: an order is always "SIP-1".
The outcome of a test example is not printed or stored (see run_eval).
"""

import argparse
import asyncio
import json
import re
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Run as a plain script, Python only searches the eval/ folder for imports.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core.llms import ChatMessage

import config
from eval import scoring
from eval.live_bar import LiveBar
from eval.llm_cache import (
    DEFAULT_CACHE_DIR,
    CachedLLM,
    DailyQuotaUsedUp,
    LiveCallLimitReached,
    NoPaidCredit,
)
from eval.run_eval import (
    DEFAULT_DB_PATH,
    GOLDEN_SET,
    RESULTS_DIR,
    build_judge,
    cached_llm,
    calls_so_far,
    count,
    judge_live_calls,
    judge_mean,
    load_golden,
    progress,
    show,
    show_score,
    source_documents,
)
from eval.terminal_table import terminal_tables
from src.agents.run_log import token_usage
from src.guardrails.guarded_llm import (
    GuardedLLM,
    build_provider_llm,
    configured_model,
)
from src.guardrails.outbound import Redactor
from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import PolicyIndex, read_sections
from src.knowledge.sql_runner import connect_read_only, run_sql

# Which groups of the golden set each baseline is run on.
BASELINES = {
    "B0": ("support", "policy"),
    "B1": ("policy",),
    "B2": ("ops",),
}
ORDER_ALIAS = "SIP-1"
TOP_K = 5
# The raw-schema baseline may read every raw table.
RAW_TABLES = (
    "orders",
    "customers",
    "order_items",
    "order_payments",
    "order_reviews",
    "products",
    "sellers",
    "geolocation",
    "product_category_name_translation",
    "return_requests",
)

# Nothing in these prompts tells the model what it cannot know: a baseline
# is the plain approach, without the care that went into the system.
POLICY_PROMPT = """\
You are the customer support assistant of MarketDesk, an online marketplace.
Always answer in Turkish, briefly. Today is {today}.
Answer the customer's question from the policy texts below, and name the
document and section you use, for example (İade Politikası, Bölüm 2).

{policies}
"""
SQL_PROMPT = """\
You write SQLite queries for the database of an online marketplace.
Today is {today}. The tables are:

{schema}

Answer the question with one SELECT statement and nothing else.
"""

# What an answer cannot know without looking the order up: an amount with
# cents, a date, what state the order is in, or a decision about it.
MADE_UP_PATTERNS = (
    r"\d+[.,]\d{2}\s*(BRL|R\$)",
    r"\b\d{1,2}[./]\d{1,2}[./]20\d{2}\b",
    r"\b20\d{2}-\d{2}-\d{2}\b",
    (
        r"sipariş\w*\s+(\S+\s+){0,5}?"
        r"(teslim edil(di|miş)|kargoya veril(di|miş)|kargoda|yolda"
        r"|iptal edil(di|miş)|hazırlan(ıyor|makta))"
    ),
    r"iade\w*\s+(\S+\s+){0,3}?(uygundur|uygunsunuz|edilebilir durumda)",
    r"(talebiniz|talebi)\s+(\S+\s+){0,3}?(oluşturul(du|muş)|açıl(dı|mış)|alın(dı|mış))",
)


def policy_text(sections: list) -> str:
    """Policy sections as the text a model reads, each under its citation."""
    return "\n\n".join(
        f"[{section['citation']}] {section['heading']}\n{section['text']}"
        for section in sections
    )


def all_sections() -> list[dict]:
    return [
        {
            "citation": section.citation,
            "heading": section.heading,
            "text": section.text,
        }
        for section in read_sections()
    ]


def raw_schema(db_path: Path | str) -> str:
    """The CREATE TABLE statements of the raw tables."""
    conn = connect_read_only(db_path)
    try:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        conn.close()
    statements = dict(rows)
    return "\n\n".join(statements[name] for name in RAW_TABLES if name in statements)


def extract_sql(answer: str) -> str:
    """The SQL of an answer, without a code fence or a closing semicolon."""
    fenced = re.search(
        r"```(?:sqlite|sql)?\s*(.*?)```", answer, re.DOTALL | re.IGNORECASE
    )
    sql = fenced.group(1) if fenced else answer
    return sql.strip().rstrip(";").strip()


def made_up(answer: str, today: str) -> bool:
    """Whether an answer states something about an order it cannot know."""
    # Today's date is in the prompt, so repeating it invents nothing.
    text = answer.replace(today, "")
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in MADE_UP_PATTERNS)


def golden_rows(db_path: Path | str, example: dict) -> list:
    conn = connect_read_only(db_path)
    try:
        return [list(row) for row in conn.execute(example["golden_sql"])]
    finally:
        conn.close()


async def complete(llm: CachedLLM, system: str, question: str) -> tuple[str, int]:
    """One model call behind the outbound guard: (answer, tokens used)."""
    guarded = GuardedLLM(inner=llm, redactor=Redactor())
    response = await guarded.achat(
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=question),
        ]
    )
    return response.message.content or "", sum(token_usage(response.raw))


def score_policy(example: dict, answer: str) -> dict:
    expected = example["expected"]
    checks = {
        "text": scoring.contains_all(answer, expected.get("must_contain", []))
        and scoring.matches_none(answer, expected.get("must_not_match", [])),
    }
    # A topic no section mentions has no source to cite.
    if "source" in example:
        sources = example["source"]
        sources = sources if isinstance(sources, list) else [sources]
        checks["source"] = any(source in answer for source in sources)
    row = {"checks": checks, "success": all(checks.values())}
    if "must_not_match" in expected:
        # The example lists what would be an invented rule.
        row["made_up"] = not scoring.matches_none(answer, expected["must_not_match"])
    return row


def score_support(example: dict, answer: str, today: str) -> dict:
    expected = example["expected"]
    invented = made_up(answer, today)
    checks = {
        "text": scoring.contains_all(answer, expected.get("must_contain", []))
        and scoring.matches_none(answer, expected.get("must_not_match", [])),
        # Without tools nothing can be looked up, so an example that
        # expects a tool call cannot be answered.
        "needs_no_tool": not expected.get("tools"),
        "nothing_made_up": not invented,
    }
    return {"checks": checks, "success": all(checks.values()), "made_up": invented}


def score_sql(example: dict, db_path: Path | str, answer: str) -> dict:
    sql = extract_sql(answer)
    result = run_sql(db_path, sql, allowed_tables=RAW_TABLES)
    matched = "rows" in result and scoring.execution_match(
        golden_rows(db_path, example), result["rows"], example.get("ordered", False)
    )
    return {
        "checks": {"execution": matched},
        "success": matched,
        "sql": sql,
        # Why it failed: the runner's error code, or rows that differ.
        "failure": None if matched else result.get("error", "DIFFERENT_ROWS"),
    }


async def run_example(
    baseline: str,
    example: dict,
    db_path: Path | str,
    index: PolicyIndex,
    llm: CachedLLM,
) -> dict:
    today = config.SIMULATED_TODAY.isoformat()
    question = example["question"].replace("{order}", ORDER_ALIAS)
    if baseline == "B2":
        system = SQL_PROMPT.format(today=today, schema=raw_schema(db_path))
    else:
        sections = all_sections() if baseline == "B0" else index.search(question, TOP_K)
        system = POLICY_PROMPT.format(today=today, policies=policy_text(sections))

    answer, tokens = await complete(llm, system, question)
    if baseline == "B2":
        row = score_sql(example, db_path, answer)
    elif example["group"] == "policy":
        row = score_policy(example, answer)
    else:
        row = score_support(example, answer, today)
    return {
        "baseline": baseline,
        "id": example["id"],
        "group": example["group"],
        "split": example.get("split", "dev"),
        # Long enough to hold a whole policy answer, which the judge reads.
        "answer": answer[:2000],
        "tokens": tokens,
        **row,
    }


def planned(examples: list[dict]) -> list[tuple[str, dict]]:
    """The (baseline, example) pairs a run goes through, in order."""
    return [
        (baseline, example)
        for baseline, groups in BASELINES.items()
        for example in examples
        if example["group"] in groups
        # B2 without golden SQL would be scored by the judge only: there are
        # no rows to compare.
        and not (baseline == "B2" and "golden_sql" not in example)
    ]


def run(
    examples: list[dict],
    db_path: Path | str,
    index: PolicyIndex,
    llm: CachedLLM,
    pause: float = 0.0,
    report=print,
    show_test: bool = False,
    judge=None,
    bar: LiveBar | None = None,
) -> list[dict]:
    """Run every baseline on the examples of its groups.

    With a judge, the policy answers are also scored for faithfulness and
    helpfulness. A bar at the bottom of the terminal, when given and
    active, follows the run; the lines then carry only their count.
    """
    rows = []
    pairs = planned(examples)
    started = time.monotonic()
    for number, (baseline, example) in enumerate(pairs, start=1):
        if bar is not None:
            bar.begin(f"{baseline} {example['id']}")
        seconds_before, live_before = llm.seconds, llm.live_calls
        row = asyncio.run(run_example(baseline, example, db_path, index, llm))
        row["seconds"] = round(llm.seconds - seconds_before, 3)
        if judge is not None and example["group"] == "policy":
            row["judge"] = judge.policy_answer(
                example["question"], row["answer"], source_documents(example)
            )
        rows.append(row)
        counter = (
            count(number, len(pairs))
            if bar is not None and bar.active
            else progress(number, len(pairs))
        )
        held_out = row["split"] == "test" and not show_test
        if held_out:
            report(f"{counter}  {baseline} {row['id']:>3}  held out")
        else:
            failed = [name for name, ok in row["checks"].items() if not ok]
            live = llm.live_calls - live_before
            report(
                f"{counter}  {baseline} {row['id']:>3}  "
                f"{'ok  ' if row['success'] else 'FAIL'}"
                + (f"  failed: {', '.join(failed)}" if failed else "")
                + f"   {calls_so_far(live, llm, judge, started)}"
            )
        if bar is not None:
            bar.finish(
                None if held_out else row["success"],
                llm.live_calls + judge_live_calls(judge),
            )
        if pause and llm.live_calls > live_before:
            time.sleep(pause)
    return rows


def summarise(rows: list[dict]) -> dict:
    """The numbers of one row of the comparison table."""

    def check_rate(name: str) -> float | None:
        return scoring.rate(
            [row["checks"][name] for row in rows if name in row["checks"]]
        )

    seconds = [row["seconds"] for row in rows]
    return {
        "examples": len(rows),
        "task_success": scoring.rate([row["success"] for row in rows]),
        "execution_accuracy": check_rate("execution"),
        "source_accuracy": check_rate("source"),
        "made_up_rate": scoring.rate(
            [row["made_up"] for row in rows if "made_up" in row]
        ),
        "faithfulness": judge_mean(rows, "faithfulness"),
        "helpfulness": judge_mean(rows, "helpfulness"),
        "steps_mean": 1.0,
        "tokens_mean": sum(row["tokens"] for row in rows) / len(rows),
        "seconds_p50": scoring.percentile(seconds, 50),
        "seconds_p95": scoring.percentile(seconds, 95),
    }


def summarise_baselines(rows: list[dict]) -> dict:
    """One summary per baseline and group, for example "B0 · policy"."""
    summary = {}
    for baseline, groups in BASELINES.items():
        for group in groups:
            chosen = [
                row
                for row in rows
                if row["baseline"] == baseline and row["group"] == group
            ]
            if chosen:
                summary[f"{baseline} · {group}"] = summarise(chosen)
    return summary


def final_rows(results_path: Path) -> dict:
    """The system's own numbers per group, read from its results file."""
    if not results_path.exists():
        return {}
    groups = json.loads(results_path.read_text(encoding="utf-8")).get(
        "summary_all_splits", {}
    )
    return {
        f"Final · {group}": {
            "made_up_rate": None,
            # Missing in a results file written without the judge.
            "faithfulness": None,
            "helpfulness": None,
            **numbers,
        }
        for group, numbers in groups.items()
        if group != "all"
    }


def markdown_table(summary: dict) -> str:
    lines = [
        (
            "| System · group | n | Task success | SQL execution | Source "
            "| Made up | Steps | Tokens | p50 s | p95 s | Faithful | Helpful |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, numbers in summary.items():
        lines.append(
            f"| {name} | {numbers['examples']} | {show(numbers['task_success'])} "
            f"| {show(numbers['execution_accuracy'])} "
            f"| {show(numbers['source_accuracy'])} "
            f"| {show(numbers['made_up_rate'])} "
            f"| {show(numbers['steps_mean'], percent=False)} "
            f"| {numbers['tokens_mean']:.0f} "
            f"| {show(numbers['seconds_p50'], percent=False)} "
            f"| {show(numbers['seconds_p95'], percent=False)} "
            f"| {show_score(numbers['faithfulness'])} "
            f"| {show_score(numbers['helpfulness'])} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--golden", type=Path, default=GOLDEN_SET)
    parser.add_argument("--only", help="comma-separated example ids, for example P1,O2")
    parser.add_argument(
        "--pause", type=float, default=12.0, help="seconds after a live call"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="ignore cached responses"
    )
    parser.add_argument(
        "--show-test",
        action="store_true",
        help="print the outcome of each test example (they then belong in dev)",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="also score the policy answers with the judge model (more quota)",
    )
    parser.add_argument(
        "--paid",
        action="store_true",
        help="make the live calls on the paid key, once the free daily quota is "
        "used up",
    )
    args = parser.parse_args()

    examples = load_golden(args.golden)
    if args.only:
        wanted = set(args.only.split(","))
        examples = [example for example in examples if example["id"] in wanted]

    provider, model = configured_model()
    index = PolicyIndex(load_embedder())
    with tempfile.TemporaryDirectory() as folder:
        cache_dir = Path(folder) / "cache" if args.no_cache else DEFAULT_CACHE_DIR
        llm = cached_llm(build_provider_llm(paid=args.paid), cache_dir, args.paid)
        print(f"Provider: {provider}   Model: {model}\n")
        judge = build_judge(cache_dir, paid=args.paid) if args.judge else None
        bar = LiveBar(len(planned(examples)))
        try:
            rows = run(
                examples,
                args.db,
                index,
                llm,
                args.pause,
                report=bar.report,
                show_test=args.show_test,
                judge=judge,
                bar=bar,
            )
        except (DailyQuotaUsedUp, LiveCallLimitReached, NoPaidCredit) as stop:
            print(f"\nStopped: {stop}")
            return 3
        finally:
            bar.close()

    name = model.replace("/", "_")
    summary = summarise_baselines(rows)
    summary.update(final_rows(RESULTS_DIR / f"golden_v1_{name}.json"))
    table = markdown_table(summary)
    print(f"\n{terminal_tables(table)}\n")
    print(f"Model calls: {llm.live_calls} live, {llm.hits} from the cache")

    if not args.only:
        RESULTS_DIR.mkdir(exist_ok=True)
        result = {
            "golden_set": args.golden.name,
            "provider": provider,
            "model": model,
            "temperature": config.LLM_TEMPERATURE,
            "summary": summary,
            # The answers of the test split are not written down.
            "examples": [row for row in rows if row["split"] == "dev"],
        }
        (RESULTS_DIR / f"baselines_v1_{name}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (RESULTS_DIR / f"baselines_v1_{name}.md").write_text(
            f"Baselines on golden set v1, {provider} `{model}`, temperature "
            f"{config.LLM_TEMPERATURE}.\n\n{table}\n\n"
            "Task success of a baseline is its own rule: for B0 on support, "
            "the text checks pass, the example needs no tool and nothing is "
            "made up; on policy, the text checks pass and the right section "
            "is cited; for B2, the rows equal the rows of the golden query. "
            '"Made up" is a pattern check, not a judgement.\n',
            encoding="utf-8",
        )
        print(f"Results written to eval/results/baselines_v1_{name}.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
