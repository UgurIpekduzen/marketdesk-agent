"""Tests for the baselines: on the synthetic database, with a stand-in model."""

import json

import pytest

import config
from eval import baselines
from eval.llm_cache import CachedLLM
from src.knowledge.sql_runner import run_sql
from tests.fakes import FakeLLM
from tests.test_run_eval import OPS_EXAMPLE, POLICY_EXAMPLE, SUPPORT_EXAMPLE

TODAY = config.SIMULATED_TODAY.isoformat()
GOOD_POLICY_ANSWER = "14 takvim günü içinde (İade Politikası, Bölüm 2)."
# One answer per call, in the order the baselines run: B0 on support and
# policy, B1 on policy, B2 on ops.
GOOD_SCRIPT = [
    "Siparişinizi göremiyorum; iade koşulları için politika geçerlidir.",
    GOOD_POLICY_ANSWER,
    GOOD_POLICY_ANSWER,
    "SELECT COUNT(*) FROM orders",
]
EXAMPLES = [SUPPORT_EXAMPLE, OPS_EXAMPLE, POLICY_EXAMPLE]


@pytest.fixture
def run(synthetic_db_path, fake_policy_index, tmp_path):
    """Run the baselines with a scripted model; returns rows and the model."""

    def run_baselines(examples, script, **options):
        fake = FakeLLM(script=list(script))
        llm = CachedLLM(inner=fake, cache_dir=tmp_path / "cache")
        rows = baselines.run(
            examples,
            synthetic_db_path,
            fake_policy_index,
            llm,
            report=options.pop("report", lambda line: None),
            **options,
        )
        return rows, fake

    return run_baselines


def system_prompt(fake: FakeLLM, call: int) -> str:
    return str(fake.requests[call]["messages"][0])


# --- Which baseline runs on what, and what it is shown ---------------------


def test_each_baseline_runs_its_groups(run):
    rows, fake = run(EXAMPLES, GOOD_SCRIPT)

    assert [(row["baseline"], row["id"]) for row in rows] == [
        ("B0", "S"),
        ("B0", "P"),
        ("B1", "P"),
        ("B2", "O"),
    ]
    assert len(fake.requests) == 4


def test_no_baseline_is_given_a_tool(run):
    _, fake = run(EXAMPLES, GOOD_SCRIPT)

    assert all(request["tools"] == [] for request in fake.requests)


def test_b0_reads_all_b1_the_closest(run):
    _, fake = run(EXAMPLES, GOOD_SCRIPT)
    sections = baselines.all_sections()

    everything, closest = system_prompt(fake, 1), system_prompt(fake, 2)

    assert all(section["citation"] in everything for section in sections)
    assert sum(section["citation"] in closest for section in sections) <= (
        baselines.TOP_K
    )
    assert len(closest) < len(everything)


def test_b2_reads_raw_tables_not_views(run):
    _, fake = run(EXAMPLES, GOOD_SCRIPT)

    schema = system_prompt(fake, 3)

    assert "CREATE TABLE" in schema
    assert "customer_unique_id" in schema
    assert "v_orders" not in schema
    assert "late_delivery_rate" not in schema


def test_order_is_an_alias_for_the_model(run):
    _, fake = run(EXAMPLES, GOOD_SCRIPT)

    question = str(fake.requests[0]["messages"][1])

    assert "SIP-1 hasarlı geldi" in question
    assert "o_day14" not in fake.sent_text()


def test_query_rows_not_sent_to_model(run):
    rows, fake = run([OPS_EXAMPLE], ["SELECT COUNT(*) FROM orders"])

    # One call writes the SQL; nothing follows it.
    assert len(fake.requests) == 1
    assert rows[0]["success"]


# --- Scoring -----------------------------------------------------------------


def test_good_answers_succeed(run):
    rows, _ = run(EXAMPLES, GOOD_SCRIPT)
    by_run = {(row["baseline"], row["id"]): row for row in rows}

    assert by_run[("B0", "P")]["success"]
    assert by_run[("B1", "P")]["success"]
    assert by_run[("B2", "O")]["success"]
    # The support example expects tool calls, which no baseline can make.
    assert not by_run[("B0", "S")]["success"]
    assert not by_run[("B0", "S")]["made_up"]


def test_policy_answer_without_source_fails(run):
    rows, _ = run([POLICY_EXAMPLE], ["14 gün içinde.", GOOD_POLICY_ANSWER])

    assert rows[0]["checks"] == {"text": True, "source": False}
    assert rows[1]["success"]


def test_sourceless_example_scored_on_text(run):
    no_source = {key: value for key, value in POLICY_EXAMPLE.items() if key != "source"}

    rows, _ = run([no_source], ["14 gün içinde.", "14 gün içinde."])

    assert rows[0]["checks"] == {"text": True}
    assert rows[0]["success"]


def test_invented_rule_counts_as_made_up(run):
    answer = "14 gün, para 5 iş günü içinde döner (İade Politikası, Bölüm 2)."
    rows, _ = run([POLICY_EXAMPLE], [answer, GOOD_POLICY_ANSWER])

    assert rows[0]["made_up"]
    assert not rows[1]["made_up"]


@pytest.mark.parametrize(
    "answer",
    [
        "İadeniz için 115,00 BRL ödenecek.",
        "Siparişiniz 12.08.2018 tarihinde ulaştı.",
        "SIP-1 numaralı siparişiniz teslim edilmiştir.",
        "Siparişiniz şu anda kargoda.",
        "Bu sipariş için iade talebiniz uygundur.",
        "İade talebiniz oluşturuldu.",
    ],
)
def test_order_statement_is_made_up(answer):
    assert baselines.made_up(answer, TODAY)


@pytest.mark.parametrize(
    "answer",
    [
        "Siparişinizi göremiyorum, sipariş numaranızla temsilciye aktarabilirim.",
        "Hasarlı ürünler teslimden sonraki 30 gün içinde iade edilebilir.",
        "500 BRL üzerindeki talepler kıdemli temsilci onayına gider.",
        f"Bugün {TODAY}; iade süresi teslim gününden başlar.",
    ],
)
def test_policy_statement_is_not_made_up(answer):
    assert not baselines.made_up(answer, TODAY)


def test_wrong_number_fails_execution(run):
    sql = "SELECT COUNT(*) FROM orders WHERE order_status = 'delivered'"
    rows, _ = run([OPS_EXAMPLE], [sql])

    assert rows[0]["failure"] == "DIFFERENT_ROWS"
    assert rows[0]["sql"] == sql


@pytest.mark.parametrize(
    ("answer", "failure"),
    [
        ("DROP TABLE orders", "SQL_REJECTED"),
        ("SELECT COUNT(*) FROM no_such_table", "SQL_REJECTED"),
        ("SELECT no_such_column FROM orders", "SQL_ERROR"),
        ("Bunu bilemiyorum.", "SQL_REJECTED"),
    ],
)
def test_broken_sql_fails_with_reason(run, answer, failure):
    rows, _ = run([OPS_EXAMPLE], [answer])

    assert not rows[0]["success"]
    assert rows[0]["failure"] == failure


def test_baseline_sql_cannot_write(run, synthetic_db_path):
    run([OPS_EXAMPLE], ["DELETE FROM orders"])

    result = run_sql(
        synthetic_db_path,
        "SELECT COUNT(*) FROM orders",
        allowed_tables=baselines.RAW_TABLES,
    )
    assert result["rows"][0][0] > 0


@pytest.mark.parametrize(
    ("answer", "sql"),
    [
        ("```sql\nSELECT 1;\n```", "SELECT 1"),
        ("```\nSELECT 1\n```", "SELECT 1"),
        ("Here it is:\n```sqlite\nSELECT 1\n```\nDone.", "SELECT 1"),
        ("  SELECT 1 ;  ", "SELECT 1"),
    ],
)
def test_sql_is_taken_out_of_the_answer(answer, sql):
    assert baselines.extract_sql(answer) == sql


# --- Splits, summary and table ---------------------------------------------


def test_test_outcome_is_not_reported(run):
    lines = []
    held_out = {**OPS_EXAMPLE, "split": "test"}

    run([held_out], ["SELECT COUNT(*) FROM orders"], report=lines.append)

    assert [line.split() for line in lines] == [
        ["[1/1]", "██████████", "100%", "B2", "O", "held", "out"]
    ]


def test_test_outcome_reported_on_request(run):
    lines = []
    held_out = {**OPS_EXAMPLE, "split": "test"}

    run(
        [held_out],
        ["SELECT COUNT(*) FROM orders"],
        report=lines.append,
        show_test=True,
    )

    assert "ok" in lines[0]


def test_summary_row_per_baseline_and_group(run):
    rows, _ = run(EXAMPLES, GOOD_SCRIPT)

    summary = baselines.summarise_baselines(rows)

    assert list(summary) == ["B0 · support", "B0 · policy", "B1 · policy", "B2 · ops"]
    assert summary["B0 · support"]["task_success"] == 0.0
    assert summary["B0 · support"]["made_up_rate"] == 0.0
    assert summary["B0 · support"]["execution_accuracy"] is None
    assert summary["B0 · policy"]["source_accuracy"] == 1.0
    assert summary["B2 · ops"]["execution_accuracy"] == 1.0
    assert summary["B2 · ops"]["made_up_rate"] is None
    assert summary["B2 · ops"]["steps_mean"] == 1.0


def test_table_dashes_meaningless_numbers(run):
    rows, _ = run(EXAMPLES, GOOD_SCRIPT)

    lines = baselines.markdown_table(baselines.summarise_baselines(rows)).splitlines()

    assert lines[0].startswith("| System · group | n | Task success | SQL execution")
    assert lines[2].startswith("| B0 · support | 1 | 0% | — | — | 0% | 1.0 |")
    assert lines[5].startswith("| B2 · ops | 1 | 100% | 100% | — | — | 1.0 |")


def test_final_rows_come_from_system_results(tmp_path):
    numbers = {
        "examples": 13,
        "task_success": 1.0,
        "execution_accuracy": 1.0,
        "source_accuracy": None,
        "steps_mean": 6.0,
        "tokens_mean": 7841.0,
        "seconds_p50": 3.1,
        "seconds_p95": 6.3,
    }
    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps({"summary_all_splits": {"ops": numbers, "all": numbers}}),
        encoding="utf-8",
    )

    final = baselines.final_rows(path)

    assert list(final) == ["Final · ops"]
    assert "| Final · ops | 13 | 100% | 100% | — | — | 6.0 | 7841 |" in (
        baselines.markdown_table(final)
    )


def test_no_final_rows_without_results(tmp_path):
    assert baselines.final_rows(tmp_path / "missing.json") == {}


# --- The judge ---------------------------------------------------------------


class StubJudge:
    # No model behind it: no live calls to count.
    live_calls = 0

    def __init__(self):
        self.seen = []

    def policy_answer(self, question, answer, documents=None):
        self.seen.append((question, answer))
        return {"faithfulness": 1.0, "helpfulness": 0.5}


def test_judge_scores_baseline_policy_only(run):
    judge = StubJudge()

    rows, _ = run(EXAMPLES, GOOD_SCRIPT, judge=judge)
    summary = baselines.summarise_baselines(rows)

    # B0 and B1 on the one policy example; not support, not B2.
    assert judge.seen == [(POLICY_EXAMPLE["question"], GOOD_POLICY_ANSWER)] * 2
    assert summary["B0 · policy"]["faithfulness"] == 1.0
    assert summary["B1 · policy"]["helpfulness"] == 0.5
    assert summary["B0 · support"]["faithfulness"] is None
    assert summary["B2 · ops"]["helpfulness"] is None
    table = baselines.markdown_table(summary).splitlines()
    assert table[0].endswith("| Faithful | Helpful |")
    assert table[3].endswith("| 1.00 | 0.50 |")
    assert table[5].endswith("| — | — |")


def test_line_counts_all_baselines_together(run):
    lines = []

    run(EXAMPLES, GOOD_SCRIPT, report=lines.append)

    total = len(baselines.planned(EXAMPLES))
    assert [line.split()[0] for line in lines] == [
        f"[{number}/{total}]" for number in range(1, total + 1)
    ]
    assert [line.split()[3] for line in lines] == [
        baseline for baseline, _ in baselines.planned(EXAMPLES)
    ]
