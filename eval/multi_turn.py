"""Play a multi-turn example: several messages and clicks in one session.

An example of the multi-turn set has turns instead of one question:

- say: a customer message, checked like a golden set example; a message
  never writes, so the requests of the order must stay as they were;
- click: the person answers the approval card, "approve" or "decline". The
  click is made in code, as the page makes it; no model takes part;
- check: only the end state.

A click and a check expect what the example has written for its order so
far (written: count, and the status, amount and reason of the row). The
example succeeds only if every turn does.
"""

import contextlib
import sqlite3
from pathlib import Path

from eval import run_eval
from eval.llm_cache import CachedLLM
from src.knowledge.policy_index import PolicyIndex
from src.mcp_server.client import OrdersClient
from src.orchestrator import Orchestrator

CLICKS = ("approve", "decline")


def last_request_id(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM return_requests").fetchone()[
        0
    ]


def written_rows(conn: sqlite3.Connection, order_id: str, after_id: int) -> list[tuple]:
    """(reason, amount, status) of the requests written for the order since
    the example started."""
    rows = conn.execute(
        "SELECT reason, refund_amount, status FROM return_requests "
        "WHERE order_id = ? AND id > ? ORDER BY id",
        (order_id, after_id),
    ).fetchall()
    return [(reason, f"{amount:.2f}", status) for reason, amount, status in rows]


def written_as_expected(rows: list[tuple], expected: dict) -> bool:
    if len(rows) != expected["count"]:
        return False
    return all(
        (reason, amount, status)
        == (expected["reason"], expected["amount"], expected["status"])
        for reason, amount, status in rows
    )


def quiet_row(name: str, text: str, checks: dict) -> dict:
    """The row of a turn without a model call, shaped like a message's so the
    rows add up."""
    return {
        "turn": name,
        "checks": checks,
        "tools_matched": 0,
        "tools_expected": 0,
        "tools_extra": 0,
        "tools_called": [],
        "intent": None,
        "answer": text,
        "llm_calls": 0,
        "tool_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


@contextlib.asynccontextmanager
async def session(
    example: dict, prepared: dict, db_path: Path, index: PolicyIndex, llm: CachedLLM
):
    """The router of one session of the example's type, open for its turns."""
    language = run_eval.language_of(example)
    if example.get("session") == "ops":
        router = Orchestrator.for_ops(db_path, llm, language)
        try:
            yield router
        finally:
            router.close()
        return
    async with OrdersClient(db_path, prepared["customer"], language) as orders:
        yield await Orchestrator.for_customer(
            orders, prepared["customer"], index, llm, language
        )


async def converse(
    example: dict,
    prepared: dict,
    db_path: Path,
    index: PolicyIndex,
    llm: CachedLLM,
    conn: sqlite3.Connection,
) -> dict:
    """Play the turns of an example in one session and score them.

    A customer session has the order server and may click; an operations
    session only talks.
    """
    order_id = prepared["order_id"]
    start_id = last_request_id(conn)
    turns = []
    async with session(example, prepared, db_path, index, llm) as router:
        pending = None
        # Tool results of the turns so far: a later turn is held to the
        # decision an earlier one got.
        earlier: list = []
        for turn in example["turns"]:
            expected = run_eval.fill(turn["expected"], prepared["placeholders"])
            written = written_rows(conn, order_id, start_id)
            if "say" in turn:
                before = run_eval.request_count(conn)
                answer = await router.ask(
                    turn["say"].replace("{order}", order_id or "")
                )
                pending = answer.awaiting_approval
                message = {**example, "question": turn["say"], "expected": expected}
                row = run_eval.score(
                    message,
                    {**prepared, "requests_before": before},
                    answer,
                    run_eval.request_count(conn),
                    earlier,
                )
                log = getattr(answer.reply, "log", None)
                earlier = [*earlier, *(log.tool_results if log else [])]
                if "written_so_far" in expected:
                    row["checks"]["written_so_far"] = (
                        len(written) == expected["written_so_far"]
                    )
                row["turn"] = "say"
            elif "click" in turn:
                if turn["click"] not in CLICKS:
                    raise ValueError(f"{example['id']}: unknown click {turn['click']}")
                # The page shows the buttons only while a request waits.
                clickable = pending is not None
                text = await (
                    router.approve() if turn["click"] == "approve" else router.decline()
                )
                pending = None
                written = written_rows(conn, order_id, start_id)
                row = quiet_row(
                    f"click {turn['click']}",
                    text,
                    {
                        "clickable": clickable,
                        "written": written_as_expected(written, expected["written"]),
                    },
                )
            else:
                row = quiet_row(
                    "check",
                    "",
                    {"written": written_as_expected(written, expected["written"])},
                )
            turns.append(row)
    return combine(example, prepared, turns)


def combine(example: dict, prepared: dict, turns: list[dict]) -> dict:
    """One row for the example: a check holds only if it held in every turn,
    and the counts add up."""
    checks: dict[str, bool] = {"label": prepared["label_ok"]}
    for turn in turns:
        for name, ok in turn["checks"].items():
            checks[name] = checks.get(name, True) and ok
    total = {
        name: sum(turn[name] for turn in turns)
        for name in (
            "tools_matched",
            "tools_expected",
            "tools_extra",
            "llm_calls",
            "tool_calls",
            "input_tokens",
            "output_tokens",
        )
    }
    return {
        "id": example["id"],
        "group": example["group"],
        "split": example.get("split", "dev"),
        "flow": example["flow"],
        "attack": None,
        "foreign_order": False,
        "question": " / ".join(
            turn["say"] for turn in example["turns"] if "say" in turn
        ),
        "success": all(checks.values()),
        "checks": checks,
        **total,
        "tools_called": [name for turn in turns for name in turn["tools_called"]],
        "intent": next((turn["intent"] for turn in turns if turn["intent"]), None),
        "answer": "\n---\n".join(turn["answer"] for turn in turns if turn["answer"]),
        "turns": [
            {
                "turn": turn["turn"],
                "success": all(turn["checks"].values()),
                "checks": turn["checks"],
                "tools_called": turn["tools_called"],
                "answer": turn["answer"],
            }
            for turn in turns
        ],
    }


def multi_turn_summary(rows: list[dict]) -> dict:
    """What the multi-turn report adds to the usual tables.

    written: (held, tried), the examples whose rows were as expected after
    every click and at the end. dev_flows: passed and run examples per flow,
    of the dev split only: a test flow's three variants test one case, so
    its count would name the case. A set may also hold single messages,
    which belong to no flow.
    """
    tried = [row for row in rows if "written" in row["checks"]]
    flows: dict[str, list[int]] = {}
    for row in rows:
        if row["split"] == "dev" and "flow" in row:
            passed, run = flows.get(row["flow"], [0, 0])
            flows[row["flow"]] = [passed + row["success"], run + 1]
    return {
        "written": [sum(row["checks"]["written"] for row in tried), len(tried)],
        "dev_flows": dict(sorted(flows.items())),
    }


def multi_turn_text(summary: dict) -> str:
    held, tried = summary["written"]
    flows = ", ".join(
        f"{flow} {passed} of {run}"
        for flow, (passed, run) in summary["dev_flows"].items()
    )
    return (
        f"Requests as expected after the clicks: {held} of {tried}\n\n"
        f"Passed per flow, dev only: {flows or 'none'}"
    )
