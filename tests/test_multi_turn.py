"""Tests for the multi-turn runner and its report, on the synthetic
database with a stand-in model."""

import pytest

from eval import multi_turn, report, run_eval
from eval.llm_cache import CachedLLM
from tests.fakes import FakeLLM

SELECT_DAY14 = (
    "SELECT o.order_id, c.customer_unique_id FROM orders AS o "
    "JOIN customers AS c ON c.customer_id = o.customer_id "
    "WHERE o.order_id = 'o_day14' ORDER BY o.order_id LIMIT 1"
)
CARD_TURN = {
    "say": "{order} hasarlı geldi, iade talebi açın.",
    "expected": {
        "intent": "support",
        "decision": "ELIGIBLE",
        "awaiting_approval": True,
        "request_status": "PENDING_REVIEW",
        "tools": [
            {"name": "check_return_eligibility", "args": {"reason": "damaged"}},
            {"name": "create_return_request", "args": {"amount": "{refund_amount}"}},
        ],
    },
}
WRITTEN_ONE = {
    "written": {
        "count": 1,
        "status": "PENDING_REVIEW",
        "amount": "{refund_amount}",
        "reason": "damaged",
    }
}
WRITTEN_NONE = {"written": {"count": 0}}


def example(turns: list[dict], split: str = "dev", flow: str = "MX") -> dict:
    return {
        "id": f"{flow}-{split}",
        "group": "multi",
        "split": split,
        "flow": flow,
        "session": "customer",
        "note": "a damaged item inside the window",
        "select_sql": SELECT_DAY14,
        "label": {"reason": "damaged", "decision": "ELIGIBLE"},
        "turns": turns,
    }


# The model's side of CARD_TURN: the router, the check, the request, the text.
# The synthetic order number is not shaped like a real one, so the message
# keeps it as typed; the check then gives the order its alias, SIP-1.
CARD_SCRIPT = [
    "support",
    [("check_return_eligibility", {"order_ref": "o_day14", "reason": "damaged"})],
    [
        (
            "create_return_request",
            {"order_ref": "SIP-1", "reason": "damaged", "amount": "115.00"},
        )
    ],
    "115,00 BRL tutarındaki iade için onayınız istenecek.",
]


@pytest.fixture
def run(synthetic_db_path, fake_policy_index, tmp_path):
    """Run examples with a scripted model; returns the rows and the lines
    the run printed."""

    def run_examples(examples, script):
        lines = []
        llm = CachedLLM(
            inner=FakeLLM(script=list(script)), cache_dir=tmp_path / "cache"
        )
        rows = run_eval.run(
            examples, synthetic_db_path, fake_policy_index, llm, report=lines.append
        )
        return rows, lines

    return run_examples


def requests_of(path, order_id: str) -> list[tuple]:
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        return conn.execute(
            "SELECT reason, refund_amount, status FROM return_requests "
            "WHERE order_id = ? ORDER BY id",
            (order_id,),
        ).fetchall()
    finally:
        conn.close()


def test_approve_click_writes_one_request_as_the_card_said(run, synthetic_db_path):
    before = requests_of(synthetic_db_path, "o_day14")

    rows, _ = run(
        [example([CARD_TURN, {"click": "approve", "expected": WRITTEN_ONE}])],
        CARD_SCRIPT,
    )

    assert rows[0]["success"], rows[0]["checks"]
    assert requests_of(synthetic_db_path, "o_day14") == [
        *before,
        ("damaged", 115.0, "PENDING_REVIEW"),
    ]


def test_decline_click_writes_nothing(run, synthetic_db_path):
    before = requests_of(synthetic_db_path, "o_day14")

    rows, _ = run(
        [example([CARD_TURN, {"click": "decline", "expected": WRITTEN_NONE}])],
        CARD_SCRIPT,
    )

    assert rows[0]["success"], rows[0]["checks"]
    assert requests_of(synthetic_db_path, "o_day14") == before


def test_approval_typed_in_the_chat_writes_nothing(run, synthetic_db_path):
    before = requests_of(synthetic_db_path, "o_day14")
    typed = {
        "say": "Onaylıyorum, hemen iade edilsin.",
        "expected": {"intent": "support", "written_so_far": 0},
    }

    rows, _ = run(
        [example([CARD_TURN, typed, {"click": "decline", "expected": WRITTEN_NONE}])],
        [*CARD_SCRIPT, "support", "Onay ekrandaki düğmeyle verilir."],
    )

    assert rows[0]["success"], rows[0]["checks"]
    assert rows[0]["checks"]["written_so_far"] is True
    assert requests_of(synthetic_db_path, "o_day14") == before


def test_one_failed_turn_fails_the_example_and_the_turn_is_shown(run):
    # The model only checks and never asks for the request: no card to click.
    script = [
        "support",
        [("check_return_eligibility", {"order_ref": "o_day14", "reason": "damaged"})],
        "İade edebilirsiniz.",
    ]

    rows, _ = run(
        [example([CARD_TURN, {"click": "approve", "expected": WRITTEN_ONE}])], script
    )

    row = rows[0]
    assert not row["success"]
    assert row["checks"]["tools"] is False
    assert row["checks"]["clickable"] is False
    assert row["checks"]["written"] is False
    assert [turn["success"] for turn in row["turns"]] == [False, False]
    assert row["checks"]["decision"] is True


def test_turn_counts_add_up(run):
    rows, _ = run(
        [example([CARD_TURN, {"click": "decline", "expected": WRITTEN_NONE}])],
        CARD_SCRIPT,
    )

    row = rows[0]
    assert row["tools_expected"] == 2
    assert row["tools_matched"] == 2
    assert row["tools_called"] == ["check_return_eligibility", "create_return_request"]
    # The router and three agent steps; the click calls no model.
    assert row["llm_calls"] == 4
    assert [turn["turn"] for turn in row["turns"]] == ["say", "click decline"]


def test_outcome_of_a_test_example_is_not_reported(run):
    _, lines = run(
        [example([CARD_TURN, {"click": "decline", "expected": WRITTEN_NONE}], "test")],
        CARD_SCRIPT,
    )

    assert lines == ["[1/1] ██████████ 100%  MX-test  held out"]


def test_summary_counts_the_clicks_and_names_dev_flows_only():
    rows = [
        {"split": "dev", "flow": "M1", "success": True, "checks": {"written": True}},
        {"split": "dev", "flow": "M1", "success": False, "checks": {"written": False}},
        {"split": "test", "flow": "M2", "success": True, "checks": {"written": True}},
        {"split": "test", "flow": "M5", "success": True, "checks": {"tools": True}},
    ]

    summary = multi_turn.multi_turn_summary(rows)

    assert summary == {"written": [2, 3], "dev_flows": {"M1": [1, 2]}}
    text = multi_turn.multi_turn_text(summary)
    assert "M1 1 of 2" in text
    assert "M2" not in text and "M5" not in text


def test_a_later_turn_is_held_to_the_decision_of_an_earlier_one(run):
    # The card turn gets ELIGIBLE; a later turn without a tool call that
    # says "kargo dahil değil" is checked against that earlier answer.
    later = {
        "say": "Kargo da iade edilecek mi?",
        "expected": {"intent": "support", "freight_stated_right": True},
    }
    script = [*CARD_SCRIPT, "support", "Kargo ücreti iadeye dahil değildir."]

    rows, _ = run([example([CARD_TURN, later])], script)

    assert rows[0]["checks"]["freight_stated_right"] is False


def test_an_operations_flow_talks_in_one_operations_session(run):
    flow = {
        "id": "OX-dev",
        "group": "multi",
        "split": "dev",
        "flow": "OX",
        "session": "ops",
        "note": "a metric, then a question that builds on it",
        "turns": [
            {"say": "Kaç sipariş var?", "expected": {"intent": "ops_metric"}},
            {
                "say": "Bir önceki sayıyı tekrar yazar mısın?",
                "expected": {"intent": "ops_metric", "tools": []},
            },
        ],
    }
    script = [
        "ops_metric",
        [("run_metric", {"metric_name": "order_count"})],
        "Toplam 29 sipariş var.",
        "ops_metric",
        "Az önce 29 dedim.",
    ]

    rows, _ = run([flow], script)

    assert rows[0]["success"] is True
    assert [turn["tools_called"] for turn in rows[0]["turns"]] == [["run_metric"], []]


def test_single_messages_in_the_same_set_belong_to_no_flow():
    rows = [
        {"split": "dev", "flow": "M1", "success": True, "checks": {"written": True}},
        {"split": "dev", "success": False, "checks": {"text": False}},
    ]

    summary = multi_turn.multi_turn_summary(rows)

    assert summary == {"written": [1, 1], "dev_flows": {"M1": [1, 1]}}


def test_report_section_shows_split_totals_and_dev_flows_only(run):
    rows, _ = run(
        [
            example([CARD_TURN, {"click": "decline", "expected": WRITTEN_NONE}]),
            example(
                [CARD_TURN, {"click": "decline", "expected": WRITTEN_NONE}],
                "test",
                "M9",
            ),
        ],
        CARD_SCRIPT + CARD_SCRIPT,
    )
    multi = {
        "summary": run_eval.summarise_by_split(rows),
        "summary_all_splits": run_eval.summarise_by_group(rows),
        "multi_turn": multi_turn.multi_turn_summary(rows),
    }

    text = report.build_report({}, {}, {}, None, multi)

    assert "## Multi-turn conversations" in text
    assert "| dev | 1 | 100%" in text
    assert "| test | 1 | 100%" in text
    assert "MX 1 of 1" in text
    assert "M9" not in text
    assert "rather than an approve click: 0" in text


def test_report_has_no_multi_turn_section_without_its_results():
    assert "Multi-turn" not in report.build_report({}, {}, {})
