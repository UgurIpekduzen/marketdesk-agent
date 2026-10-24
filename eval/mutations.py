"""Do the tests and the attack sets notice when a guard is switched off?

Usage:  python eval/mutations.py                 the unit tests, for every guard
        python eval/mutations.py --only NAME     one guard
        python eval/mutations.py --list          the guards and what breaks

A set of attacks that passes tells nothing if it would pass without the guard
too. So each guard is broken on purpose, in the running process and never in
the source, and the tests that are meant to watch it are run: they have to
fail. A broken guard whose tests all pass is a hole in the tests, and the
report names it.

A guard is broken by a patch. The same patch is applied in the test process
and, for the guards that live in the order server, in the server's process
(eval/mutated_server.py is started in place of the real one). Nothing here is
imported by the application.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
MUTATION_VARIABLE = "MARKETDESK_MUTATION"
PLUGIN = "eval.mutation_plugin"
CONTROL = "control_nothing_broken"


@dataclass(frozen=True)
class Mutation:
    name: str
    breaks: str  # what is switched off, in a sentence
    patch: Callable[[ExitStack], None]
    unit_tests: tuple[str, ...]  # the test files meant to watch this guard
    # The patch also has to be applied in the order server's own process.
    server_side: bool = False
    # (attack file, example ids) that run the guard with the model; empty
    # where no attack through the model can reach the guard.
    live: tuple[tuple[str, tuple[str, ...]], ...] = ()


# --- The patches ----------------------------------------------------------------


def patch_attr(stack: ExitStack, target, name: str, value) -> None:
    stack.enter_context(mock.patch.object(target, name, value))


def approval_off(stack: ExitStack) -> None:
    """Any token, or none, is a person's approval."""
    from src.guardrails.approval import Approvals

    patch_attr(stack, Approvals, "consume", lambda self, token, action: True)


def existence_leak(stack: ExitStack) -> None:
    """An order of another customer answers differently from a missing one."""
    import sqlite3

    from src import messages
    from src.mcp_server import server as server_module
    from src.tools import orders

    original = orders.get_order_status

    def leaking(session, conn, order_ref, *args, **kwargs):
        answer = original(session, conn, order_ref, *args, **kwargs)
        if answer.get("error") == "NOT_FOUND":
            exists = conn.execute(
                "SELECT 1 FROM orders WHERE order_id = ?",
                (session.order_id_for(order_ref),),
            ).fetchone()
            if exists:
                return {
                    "error": "NOT_FOUND",
                    "message": messages.ORDER_NOT_FOUND + " (it is another customer's)",
                }
        return answer

    assert sqlite3  # the leak reads the table the real check reads
    patch_attr(stack, orders, "get_order_status", leaking)
    patch_attr(stack, server_module, "get_order_status", leaking)


def validator_tables_off(stack: ExitStack) -> None:
    """Free SQL may read any table of the database, not only the safe views."""
    from src.knowledge import sql_validator

    original = sql_validator.check_tree

    def anything_in_the_database(tree, allowed_tables, reserved_names):
        return original(tree, (*allowed_tables, *reserved_names), reserved_names)

    patch_attr(stack, sql_validator, "check_tree", anything_in_the_database)


def theme_check_off(stack: ExitStack) -> None:
    """Any quote is accepted as a piece of a review, cut or made up."""
    from src.knowledge import review_themes

    patch_attr(stack, review_themes, "whole_sentences", lambda review, quote: True)


def outbound_off(stack: ExitStack) -> None:
    """Text leaves for the model provider as it is, personal data and all."""
    from collections import Counter as Count

    from src.guardrails.outbound import Redactor

    patch_attr(stack, Redactor, "redact", lambda self, text: (text, Count()))


def write_allowlist_off(stack: ExitStack) -> None:
    """The database connections may write anywhere."""
    from src.guardrails import write_access
    from src.mcp_server import server as server_module
    from src.tools import review_queue

    def open_connection(conn, inserts=(), updates=()):
        return conn

    patch_attr(stack, write_access, "restrict_writes", open_connection)
    patch_attr(stack, server_module, "restrict_writes", open_connection)
    patch_attr(stack, review_queue, "restrict_writes", open_connection)


class AnyIntent(frozenset):
    """A set of intents that holds every intent, compared as the real one."""

    def __contains__(self, item: object) -> bool:
        return True


def router_roles_off(stack: ExitStack) -> None:
    """A session may be routed to any agent."""
    from src import orchestrator

    everything = {
        session_type: AnyIntent(intents)
        for session_type, intents in orchestrator.ALLOWED_INTENTS.items()
    }
    patch_attr(stack, orchestrator, "ALLOWED_INTENTS", everything)


def critic_off(stack: ExitStack) -> None:
    """The numbers of an answer are not checked against the tools."""
    import config

    patch_attr(stack, config, "CRITIC_ENABLED", False)


def safe_markdown_off(stack: ExitStack) -> None:
    """The model's text goes to the page as it is, links and images included."""
    from src.ui import view

    patch_attr(stack, view, "safe_markdown", lambda text, language=None: text)


def card_binding_off(stack: ExitStack) -> None:
    """A click writes whatever request waits, not the card the person saw."""
    from src.mcp_server.client import OrdersClient

    original = OrdersClient.approve_pending

    async def any_card(self, card):
        # The click carries the card that waits now, not the one it was on.
        return await original(self, await self.pending_approval())

    patch_attr(stack, OrdersClient, "approve_pending", any_card)


def nothing(stack: ExitStack) -> None:
    """Breaks nothing: the control of the method."""


MUTATIONS = {
    mutation.name: mutation
    for mutation in (
        Mutation(
            "control_nothing_broken",
            "nothing (the control: its tests must pass)",
            nothing,
            ("tests/test_critic.py", "tests/test_approval.py"),
        ),
        Mutation(
            "approval_off",
            "the approval token is not checked: a request is written without a click",
            approval_off,
            ("tests/test_approval.py", "tests/test_return_requests.py"),
            server_side=True,
            live=(
                ("eval/golden_set.jsonl", ()),
                ("eval/multi_turn_set.jsonl", ()),
                ("eval/multi_turn_attacks.jsonl", ()),
            ),
        ),
        Mutation(
            "existence_leak",
            "an order of another customer answers differently from a missing one",
            existence_leak,
            ("tests/test_orders.py", "tests/test_leak.py"),
            server_side=True,
            live=(
                ("eval/golden_set.jsonl", ()),
                ("eval/injection_tests.jsonl", ()),
            ),
        ),
        Mutation(
            "validator_tables_off",
            "free SQL may read any table, not only the safe views",
            validator_tables_off,
            ("tests/test_sql_validator.py", "tests/test_sql_runner.py"),
            live=(
                ("eval/injection_tests.jsonl", ()),
                ("eval/indirect_injection_tests.jsonl", ()),
            ),
        ),
        Mutation(
            "theme_check_off",
            "any quote is accepted as a piece of a review",
            theme_check_off,
            ("tests/test_review_themes.py",),
            live=(("eval/review_insight_tests.jsonl", ()),),
        ),
        Mutation(
            "outbound_off",
            "personal data is not masked before the text leaves for the provider",
            outbound_off,
            (
                "tests/test_outbound.py",
                "tests/test_pii.py",
                "tests/test_leak.py",
            ),
        ),
        Mutation(
            "write_allowlist_off",
            "the database connections may write to any table",
            write_allowlist_off,
            ("tests/test_write_access.py", "tests/test_review_queue.py"),
            server_side=True,
        ),
        Mutation(
            "router_roles_off",
            "the router lets a session reach any agent",
            router_roles_off,
            ("tests/test_orchestrator.py",),
            live=(
                ("eval/golden_set.jsonl", ()),
                ("eval/injection_tests.jsonl", ()),
            ),
        ),
        Mutation(
            "critic_off",
            "the numbers of an answer are not checked against the tools",
            critic_off,
            ("tests/test_critic.py",),
            live=(("eval/number_traps.jsonl", ()),),
        ),
        Mutation(
            "safe_markdown_off",
            "the model's links and images reach the page as they are",
            safe_markdown_off,
            ("tests/test_view.py",),
            live=(("eval/client_layer_tests.jsonl", ()),),
        ),
        Mutation(
            "card_binding_off",
            "a click writes the request that waits, not the card the person saw",
            card_binding_off,
            ("tests/test_mcp_server.py", "tests/test_chat_session.py"),
        ),
    )
}


def apply(name: str, stack: ExitStack) -> None:
    """Break the guard of this name, for as long as the stack is open."""
    MUTATIONS[name].patch(stack)


def apply_everywhere(name: str, stack: ExitStack) -> None:
    """Break the guard here and, if it lives in the order server, there too.

    The order server is a process of its own, started from the client; the
    mutated one is started in its place.
    """
    apply(name, stack)
    if not MUTATIONS[name].server_side:
        return
    from mcp.client.stdio import StdioServerParameters

    from src.mcp_server import client

    original = client.server_parameters

    def mutated_server(env=None):
        parameters = original(env)
        return StdioServerParameters(
            command=parameters.command,
            args=["-m", "eval.mutated_server", name],
            cwd=parameters.cwd,
            env=parameters.env,
        )

    stack.callback(setattr, client, "server_parameters", original)
    client.server_parameters = mutated_server


# --- The runner -------------------------------------------------------------------


def unit_run(mutation: Mutation) -> dict:
    """Run the tests meant to watch a guard, with the guard broken."""
    environment = {**os.environ, MUTATION_VARIABLE: mutation.name}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-n",
        "0",
        "-p",
        PLUGIN,
        *mutation.unit_tests,
    ]
    done = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    failed = [line for line in done.stdout.splitlines() if line.startswith("FAILED")]
    return {
        "killed": done.returncode != 0 and bool(failed),
        "tests_failed": [
            line.split(" - ")[0].removeprefix("FAILED ") for line in failed
        ],
        "returncode": done.returncode,
        "summary": next(
            (line for line in reversed(done.stdout.splitlines()) if " in " in line),
            "",
        ),
    }


def dev_ids(path: str) -> str:
    """The ids of the dev examples of an attack set, comma separated.

    Only the dev split is run on a broken system: the test split stays held out.
    """
    lines = (PROJECT_ROOT / path).read_text(encoding="utf-8").splitlines()
    return ",".join(
        row["id"] for row in map(json.loads, lines) if row.get("split") == "dev"
    )


def eval_rows(name: str, golden: str, ids: str, paid: bool) -> list[dict]:
    """The rows of a run of the evaluation with the guard of this name broken."""
    with tempfile.TemporaryDirectory() as folder:
        rows_file = Path(folder) / "rows.json"
        command = [
            sys.executable,
            "-m",
            "eval.mutated_eval",
            name,
            "--golden",
            golden,
            "--only",
            ids,
            "--pause",
            "0",
            *(["--paid"] if paid else []),
        ]
        subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env={**os.environ, "MARKETDESK_MUTATION_ROWS": str(rows_file)},
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        if not rows_file.exists():
            raise RuntimeError(f"{name} on {golden}: the run wrote no rows")
        return json.loads(rows_file.read_text(encoding="utf-8"))


def live_run(mutation: Mutation, paid: bool) -> dict:
    """Run the attack sets with the guard broken and with nothing broken.

    The guard is noticed when an example that passes with nothing broken
    fails with the guard broken. The run with nothing broken comes from the
    cache; the one with the guard broken asks the model where the broken
    guard changes what the model is told.
    """
    if not mutation.live:
        return {"killed": None, "failed": [], "sets": []}
    failed, sets = [], []
    for golden, ids in mutation.live:
        wanted = ",".join(ids) if ids else dev_ids(golden)
        base = {r["id"]: r for r in eval_rows(CONTROL, golden, wanted, paid)}
        broken = {r["id"]: r for r in eval_rows(mutation.name, golden, wanted, paid)}
        sets.append(Path(golden).name)
        for example, row in broken.items():
            if base[example]["success"] and not row["success"]:
                failed.append(
                    {
                        "set": Path(golden).name,
                        "example": example,
                        "checks": row["failed"],
                    }
                )
    return {"killed": bool(failed), "failed": failed, "sets": sets}


def live_text(row: dict) -> str:
    live = row.get("live")
    if live is None:
        return "not run"
    if live["killed"] is None:
        return "no attack through the model reaches this guard"
    if live["killed"]:
        names = ", ".join(f"{f['set']} {f['example']}" for f in live["failed"][:6])
        return f"noticed ({len(live['failed'])} examples fail: {names})"
    return "**not noticed** by " + ", ".join(live["sets"])


def markdown(results: dict) -> str:
    lines = [
        "# Do the tests notice a guard that is switched off?",
        "",
        (
            "Each guard is broken in the running process (never in the source) and "
            "the tests meant to watch it are run. A guard whose tests still pass "
            "when it is broken is a hole in the tests."
        ),
        "",
        "| Guard broken | What is switched off | Unit tests | Attack sets (dev, with the model) |",
        "|---|---|---|---|",
    ]
    for name, row in results.items():
        mutation = MUTATIONS[name]
        files = ", ".join(Path(f).name for f in mutation.unit_tests)
        if name == CONTROL:
            result = (
                "tests fail: **the method is broken**"
                if row["killed"]
                else "tests pass, as they must"
            )
        elif row["killed"]:
            result = f"noticed ({len(row['tests_failed'])} failed first)"
        else:
            result = "**not noticed**"
        lines.append(
            f"| `{name}` | {mutation.breaks} | {files}: {result} | {live_text(row)} |"
        )
    guards = {n: r for n, r in results.items() if n != CONTROL}
    survived = [name for name, row in guards.items() if not row["killed"]]
    lines += [
        "",
        f"Noticed by the unit tests: {len(guards) - len(survived)} of {len(guards)}.",
    ]
    if survived:
        lines.append("Not noticed: " + ", ".join(f"`{n}`" for n in survived) + ".")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="the name of one guard")
    parser.add_argument("--list", action="store_true", help="list the guards")
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run the attack sets with the model on each broken guard "
        "(uses LLM quota)",
    )
    parser.add_argument(
        "--paid", action="store_true", help="with --live: finish on the paid key"
    )
    args = parser.parse_args()

    if args.list:
        for mutation in MUTATIONS.values():
            side = "server" if mutation.server_side else "process"
            print(f"{mutation.name:24} [{side}] {mutation.breaks}")
        return 0
    if args.only and args.only not in MUTATIONS:
        parser.error(f"unknown guard {args.only!r}; see --list")

    names = [args.only] if args.only else list(MUTATIONS)
    results = {}
    for name in names:
        print(f"breaking {name} ...", flush=True)
        results[name] = unit_run(MUTATIONS[name])
        state = "noticed" if results[name]["killed"] else "NOT NOTICED"
        print(f"  {state}: {results[name]['summary']}", flush=True)
        if args.live and name != CONTROL:
            results[name]["live"] = live_run(MUTATIONS[name], args.paid)
            print(f"  attack sets: {live_text(results[name])}", flush=True)

    if not args.only:
        RESULTS_DIR.mkdir(exist_ok=True)
        (RESULTS_DIR / "mutations_v1.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (RESULTS_DIR / "mutations_v1.md").write_text(
            markdown(results), encoding="utf-8"
        )
        print("Results written to eval/results/mutations_v1.json and .md")
    guards = [row for name, row in results.items() if name != CONTROL]
    counts = Counter(row["killed"] for row in guards)
    print(f"noticed {counts[True]} of {len(guards)}")
    control = results.get(CONTROL)
    return 1 if control and control["killed"] else 0


if __name__ == "__main__":
    sys.exit(main())
