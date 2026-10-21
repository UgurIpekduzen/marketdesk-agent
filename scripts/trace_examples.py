"""Send example traces of every error kind to the tracing target.

Usage:  python scripts/trace_examples.py [--target langfuse|phoenix]

Fills a tracing tool with one trace per kind of error the project marks
(a refused message, the step and tool limits, a quota or busy provider, a rejected or
failing query, a repeated call, a missing order, an approval asked for,
approved and declined, a duplicate request), so its views can be built and
shown without waiting for real failures. Uses the stand-in model and
embedder of the tests on a synthetic database built in a temporary folder:
no model call, no API quota, no Olist data.
"""

import argparse
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path

# Run as a plain script, Python only searches the scripts/ folder for imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from scripts import load_sqlite
from src import tracing
from src.knowledge.policy_index import PolicyIndex, build_index
from src.mcp_server.client import OrdersClient
from src.orchestrator import Orchestrator
from tests import synthetic_data
from tests.fakes import FakeEmbedder, FakeLLM
from tests.synthetic_data import ALICE
from tests.test_load_sqlite import write_raw

COUNT = [("run_metric", {"metric_name": "order_count"})]
EACH_STATE = [
    [("run_metric", {"metric_name": "order_count", "customer_state": [str(n)]})]
    for n in range(config.MAX_STEPS + 2)
]
RETURN = {"order_ref": "o_day14", "reason": "damaged", "amount": "115.00"}
ASK_RETURN = ["support", [("create_return_request", RETURN)], "Onayınız istenecek."]

# Operations session: the model's script and the question.
OPS_EXAMPLES = {
    "answered": (["ops_metric", COUNT, "29 sipariş."], "Kaç sipariş var?"),
    "refused, support": (["support"], "SIP-1 nerede?"),
    "refused, out of scope": (["out_of_scope"], "Bana bir şiir yaz."),
    "query rejected": (
        [
            "ops_metric",
            [("run_sql", {"query": "DROP TABLE orders"})],
            [("run_sql", {"query": "SELECT COUNT(*) FROM v_orders"})],
            "29 sipariş.",
        ],
        "SQL ile kaç sipariş var?",
    ),
    "query failed": (
        [
            "ops_metric",
            [("run_sql", {"query": "SELECT nope FROM v_orders"})],
            "Olmadı.",
        ],
        "Bir sütunu say.",
    ),
    "repeated call": (["ops_metric", COUNT, COUNT, COUNT, "29."], "Kaç sipariş var?"),
    "step limit": (["ops_metric", *EACH_STATE], "Her eyalet için tek tek say."),
    "tool limit": (
        ["ops_metric", [call for [call] in EACH_STATE] * 2, "Bitti."],
        "Hepsini aynı anda say.",
    ),
    "quota": (
        ["ops_metric", RuntimeError("429 RESOURCE_EXHAUSTED")],
        "Kaç sipariş var?",
    ),
    "busy": (["ops_metric", RuntimeError("503 UNAVAILABLE")], "Kaç sipariş var?"),
}
# Customer session: the model's script, the message, then a click if any.
CUSTOMER_EXAMPLES = {
    "order not found": (
        ["support", [("get_order_status", {"order_ref": "o_nope"})], "Bulamadım."],
        "o_nope nerede?",
        None,
    ),
    "refused, ops": (["ops_metric"], "Toplam ciro ne kadar?", None),
    "approval declined": (
        ASK_RETURN,
        "o_day14 hasarlı geldi, iade istiyorum",
        "decline",
    ),
    "approval approved": (
        ASK_RETURN,
        "o_day14 hasarlı geldi, iade istiyorum",
        "approve",
    ),
    "duplicate request": (ASK_RETURN, "o_day14 için yine iade istiyorum", None),
}


async def run_examples(db_path: Path, index: PolicyIndex) -> None:
    """Send every example through a router, one session each."""
    for name, (script, question) in OPS_EXAMPLES.items():
        router = Orchestrator.for_ops(db_path, FakeLLM(script=script))
        try:
            await router.ask(question)
        except RuntimeError:
            pass  # the provider failures are meant to fail
        finally:
            router.close()
        print("sent", name)
    for name, (script, message, click) in CUSTOMER_EXAMPLES.items():
        async with OrdersClient(db_path, ALICE, "tr") as orders:
            router = await Orchestrator.for_customer(
                orders, ALICE, index, FakeLLM(script=script), "tr"
            )
            await router.ask(message)
            if click:
                await getattr(router, click)()
        print("sent", name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=["langfuse", "phoenix"], default="langfuse")
    target = parser.parse_args().target

    folder = Path(tempfile.mkdtemp())
    try:
        db_path = folder / "synthetic.db"
        raw_dir = write_raw(folder / "raw", synthetic_data.build_rows())
        load_sqlite.build_database(raw_dir, db_path, config.SIMULATED_TODAY)
        build_index(FakeEmbedder(), folder / "index")
        index = PolicyIndex(FakeEmbedder(), folder / "index")
        tracing.setup_tracing(target)
        asyncio.run(run_examples(db_path, index))
    finally:
        tracing.shutdown_tracing()
        shutil.rmtree(folder)


if __name__ == "__main__":
    main()
