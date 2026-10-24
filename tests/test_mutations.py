"""Tests for the mutation test: that each guard really is broken while the
mutation is on, that it is whole again afterwards, and that the report says
what happened. No model, no network."""

import json
from contextlib import ExitStack
from pathlib import Path

from eval import mutations
from eval.mutations import CONTROL, MUTATIONS, apply, apply_everywhere
from tests.synthetic_data import ALICE

ROOT = Path(__file__).resolve().parent.parent


def test_every_guard_names_the_tests_and_the_attack_sets_that_watch_it():
    for mutation in MUTATIONS.values():
        assert mutation.unit_tests, mutation.name
        for path in mutation.unit_tests:
            assert (ROOT / path).exists(), (mutation.name, path)
        for golden, ids in mutation.live:
            rows = [
                json.loads(line)
                for line in (ROOT / golden).read_text(encoding="utf-8").splitlines()
            ]
            known = {row["id"] for row in rows}
            assert set(ids) <= known, (mutation.name, golden)
            assert mutations.dev_ids(golden), (mutation.name, golden)


def test_the_control_breaks_nothing_and_there_is_one_only():
    assert CONTROL in MUTATIONS
    assert MUTATIONS[CONTROL].live == ()
    assert [name for name in MUTATIONS if "control" in name] == [CONTROL]


def test_only_the_dev_split_is_run_on_a_broken_system():
    ids = mutations.dev_ids("eval/golden_set.jsonl").split(",")
    rows = [
        json.loads(line)
        for line in (ROOT / "eval/golden_set.jsonl").read_text().splitlines()
    ]

    assert set(ids) == {row["id"] for row in rows if row["split"] == "dev"}
    assert not set(ids) & {row["id"] for row in rows if row["split"] == "test"}


def test_each_patch_changes_a_behaviour_and_restores_it():
    from collections import Counter

    from src import orchestrator
    from src.guardrails.approval import Approvals, ReturnAction
    from src.guardrails.outbound import Redactor
    from src.knowledge import review_themes, sql_validator
    from src.knowledge.sql_validator import SqlRejected, validate
    from src.orchestrator import Intent, SessionType

    action = ReturnAction("o1", "damaged", __import__("decimal").Decimal("1.00"))
    raw_tables = ("customers", "orders")

    def refuses_raw_table() -> bool:
        try:
            validate("SELECT * FROM customers", raw_tables)
        except SqlRejected:
            return True
        return False

    assert Approvals().consume(None, action) is False
    assert Redactor().redact("a@b.com")[1] == Counter({"email": 1})
    assert refuses_raw_table()
    assert not review_themes.whole_sentences("Não recebi.", "recebi")
    assert Intent.OPS_METRIC not in orchestrator.ALLOWED_INTENTS[SessionType.CUSTOMER]

    with ExitStack() as stack:
        for name in (
            "approval_off",
            "outbound_off",
            "validator_tables_off",
            "theme_check_off",
            "router_roles_off",
        ):
            apply(name, stack)

        assert Approvals().consume(None, action) is True
        assert Redactor().redact("a@b.com")[1] == Counter()
        assert not refuses_raw_table()
        assert review_themes.whole_sentences("Não recebi.", "recebi")
        assert Intent.OPS_METRIC in orchestrator.ALLOWED_INTENTS[SessionType.CUSTOMER]

    assert Approvals().consume(None, action) is False
    assert Redactor().redact("a@b.com")[1] == Counter({"email": 1})
    assert refuses_raw_table()
    assert not review_themes.whole_sentences("Não recebi.", "recebi")
    assert Intent.OPS_METRIC not in orchestrator.ALLOWED_INTENTS[SessionType.CUSTOMER]
    assert sql_validator.check_tree  # the original function is back


def test_a_guard_of_the_order_server_is_broken_in_the_server_process(
    synthetic_db_path,
):
    from tests.test_mcp_server import RETURN, request_count, with_server

    async def scenario(orders):
        # No click: the real server answers APPROVAL_REQUIRED and writes nothing.
        return await orders.call("create_return_request", RETURN)

    normal = with_server(synthetic_db_path, scenario)
    assert normal["error"] == "APPROVAL_REQUIRED"
    before = request_count(synthetic_db_path)

    with ExitStack() as stack:
        apply_everywhere("approval_off", stack)
        broken = with_server(synthetic_db_path, scenario)

    # The mutated server wrote the request with no approval at all.
    assert "error" not in broken
    assert request_count(synthetic_db_path) == before + 1


def test_the_client_is_whole_again_after_a_server_mutation():
    from src.mcp_server import client

    original = client.server_parameters
    with ExitStack() as stack:
        apply_everywhere("approval_off", stack)
        assert client.server_parameters is not original
        assert "eval.mutated_server" in client.server_parameters().args
    assert client.server_parameters is original
    assert ALICE  # the fixture customer exists


def test_the_report_names_the_guards_the_tests_did_not_notice():
    results = {
        CONTROL: {"killed": False, "tests_failed": [], "summary": "ok"},
        "approval_off": {
            "killed": True,
            "tests_failed": ["tests/test_approval.py::test_x"],
            "summary": "1 failed",
            "live": {
                "killed": True,
                "failed": [{"set": "golden_set.jsonl", "example": "S2", "checks": []}],
                "sets": ["golden_set.jsonl"],
            },
        },
        "outbound_off": {
            "killed": False,
            "tests_failed": [],
            "summary": "ok",
            "live": {"killed": None, "failed": [], "sets": []},
        },
        "critic_off": {
            "killed": True,
            "tests_failed": ["a"],
            "summary": "x",
            "live": {"killed": False, "failed": [], "sets": ["number_traps.jsonl"]},
        },
    }

    text = mutations.markdown(results)

    assert "Noticed by the unit tests: 2 of 3." in text
    assert "Not noticed: `outbound_off`." in text
    assert "tests pass, as they must" in text
    assert "noticed (1 examples fail: golden_set.jsonl S2)" in text
    assert "no attack through the model reaches this guard" in text
    assert "**not noticed** by number_traps.jsonl" in text
