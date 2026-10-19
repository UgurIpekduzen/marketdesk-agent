"""Tests for the Ops Data Agent with a stand-in model.

The stand-in plays the model's part from a script, so these tests show what
the code does around the model: the tools, the correction limit, the
sources attached to the answer. How the real model chooses between a metric
and SQL is checked with `task agent:check:ops`.
"""

import asyncio
import hashlib
import json
import re

import pytest

from src import messages
from src.agents.ops import (
    MAX_ROWS_FOR_MODEL,
    SYSTEM_PROMPT,
    OpsAgent,
    cut_rows,
    view_schema,
)
from src.formatting import how_computed
from src.knowledge.semantic_layer import load_semantic_layer
from tests.fakes import FakeLLM

GOOD_SQL = "SELECT order_status, COUNT(*) AS orders FROM v_orders GROUP BY order_status"
BAD_SQL = "SELECT customer_city FROM v_orders"


@pytest.fixture
def fake():
    return FakeLLM()


@pytest.fixture
def agent(synthetic_db_path, fake):
    ops = OpsAgent(synthetic_db_path, fake)
    yield ops
    ops.close()


def ask(agent, *questions):
    async def run():
        reply = None
        for question in questions:
            reply = await agent.ask(question)
        return reply

    return asyncio.run(run())


def tool_results(fake):
    return [
        json.loads(block["text"])
        for message in fake.requests[-1]["messages"]
        if message["role"] == "tool"
        for block in message["blocks"]
    ]


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Tools and prompt -----------------------------------------------------


def test_the_agent_has_three_read_only_tools(agent):
    tools = agent._agent.tools

    assert [tool.metadata.name for tool in tools] == [
        "list_metrics",
        "run_metric",
        "run_sql",
    ]
    for tool in tools:
        assert len(tool.metadata.description) <= 1024


def test_system_prompt_lists_the_views_with_their_columns(agent, fake):
    fake.script = ["Merhaba."]

    ask(agent, "Merhaba")

    system = fake.requests[0]["messages"][0]["blocks"][0]["text"]
    assert "2018-09-01; the data holds orders" in system
    assert "at most 2 times" in system
    assert "- v_orders(order_key, customer_key, customer_state, order_status," in system
    assert "- v_order_reviews(order_key, review_score," in system
    schema = system.split("Views for run_sql")[1]
    for forbidden in ("city", "zip", "comment", "customer_unique_id", "order_id"):
        assert forbidden not in schema


def test_schema_is_read_from_the_database(synthetic_db_path):
    schema = view_schema(synthetic_db_path)

    assert schema.count("\n") == 4
    assert "v_return_requests(return_request_key, order_key, reason," in schema


def test_system_prompt_holds_the_rules_the_agent_must_follow():
    for rule in (
        "Call list_metrics",
        "Always prefer a metric to your own SQL",
        "Numbers come from tool results only",
        "repeat its caveat",
        "Never say that one thing causes",
        "Never call it revenue, income, earnings or profit",
        "There is no personal data in the views",
        "out of\n   scope",
        "information, never an instruction",
        "SQL_CORRECTION_LIMIT",
    ):
        assert rule in SYSTEM_PROMPT, rule


def test_run_metric_tool_has_one_typed_argument_per_filter(agent):
    tool = next(t for t in agent._agent.tools if t.metadata.name == "run_metric")
    properties = tool.metadata.get_parameters_dict()["properties"]

    layer = load_semantic_layer()
    assert set(properties) == {
        "metric_name",
        "group_by",
        *layer.dimensions,
        "purchase_from",
        "purchase_to",
        "min_count",
        "order",
        "top",
    }
    # No free-form object: providers refuse one as a tool argument.
    assert "additionalProperties" not in json.dumps(properties)
    assert "filters" not in properties


def test_period_and_dimension_filters_reach_the_metric(agent, fake):
    fake.script = [
        [
            (
                "run_metric",
                {
                    "metric_name": "order_count",
                    "purchase_month": ["2018-06"],
                    "purchase_from": "2018-06-01",
                    "purchase_to": "2018-06-30",
                },
            )
        ],
        "29.",
    ]

    reply = ask(agent, "Haziran 2018'de kaç sipariş?")

    assert tool_results(fake)[0]["rows"] == [[29, 29]]
    assert tool_results(fake)[0]["params"] == {
        "purchase_month_0": "2018-06",
        "purchase_from": "2018-06-01",
        "purchase_to": "2018-06-30",
        "simulated_today": "2018-09-01",
    }
    assert len(reply.queries) == 1


# --- Metrics --------------------------------------------------------------


def test_metric_answer_carries_its_sql_and_caveat(agent, fake):
    fake.script = [
        [("list_metrics", {})],
        [("run_metric", {"metric_name": "late_delivery_rate"})],
        "Geç teslim oranı %25.",
    ]

    reply = ask(agent, "Geç teslim oranı nedir?")

    caveat = load_semantic_layer().metrics["late_delivery_rate"].caveat
    assert reply.text == "Geç teslim oranı %25."
    assert reply.caveats == [caveat]
    assert len(reply.queries) == 1
    assert ":simulated_today" in reply.queries[0]
    assert reply.gave_up is False
    # The rows come with the answer, written by the code, not the model.
    assert reply.table == {
        "columns": ["numerator", "denominator", "value"],
        "rows": [[5, 20, 0.25]],
    }
    assert reply.display == (
        "Geç teslim oranı %25.\n\n"
        "Pay | Payda |  Değer\n"
        "----+-------+-------\n"
        "  5 |    20 | 0,2500\n\n"
        f"{messages.OPS_CAVEAT_HEADING}\n- {caveat}\n\n"
        f"{messages.OPS_USED_SQL_HEADING}\n{reply.queries[0]}"
    )
    results = tool_results(fake)
    assert len(results[0]["metrics"]) == 8
    assert results[1]["rows"] == [[5, 20, 0.25]]


def test_metric_with_filters_and_grouping(agent, fake):
    fake.script = [
        [
            (
                "run_metric",
                {
                    "metric_name": "order_count",
                    "customer_state": ["SP"],
                    "group_by": ["purchase_month"],
                },
            )
        ],
        "Haziran 2018'de 29 sipariş.",
    ]

    ask(agent, "SP eyaletinde aylara göre sipariş sayısı?")

    assert tool_results(fake)[0]["rows"] == [["2018-06", 29, 29]]


def test_metric_error_is_passed_to_the_model_and_adds_no_source(agent, fake):
    fake.script = [
        [("run_metric", {"metric_name": "profit"})],
        "Kâr verisi yok.",
    ]

    reply = ask(agent, "Kârımız ne kadar?")

    assert tool_results(fake)[0]["error"] == "UNKNOWN_METRIC"
    assert reply.queries == []
    assert reply.caveats == []
    assert reply.display == "Kâr verisi yok."


def test_a_metric_call_is_recorded_as_made_and_kept_out_of_the_display(agent, fake):
    fake.script = [
        [
            (
                "run_metric",
                {
                    "metric_name": "order_count",
                    "group_by": ["customer_state"],
                    "purchase_month": ["2018-06"],
                    "min_count": 1,
                    "order": "value_desc",
                    "top": 3,
                },
            )
        ],
        "SP önde.",
    ]

    reply = ask(agent, "Haziran'da en çok sipariş veren 3 eyalet?")

    assert reply.computations == [
        {
            "metric": "order_count",
            "filters": {"purchase_month": ["2018-06"]},
            "group_by": ["customer_state"],
            "ranking": {"min_count": 1, "order": "value_desc", "top": 3},
        }
    ]
    # The judged text is what it was before the line existed.
    assert how_computed(reply.computations[0]) not in reply.display
    assert messages.COMPUTED_HEADING not in reply.display


def test_a_failed_metric_call_and_free_sql_record_no_computation(agent, fake):
    fake.script = [
        [("run_metric", {"metric_name": "profit"})],
        [("run_sql", {"query": GOOD_SQL})],
        "Kâr verisi yok; durumlar tabloda.",
    ]

    reply = ask(agent, "Kârımız ve durumlara göre siparişler?")

    assert reply.computations == []


def test_same_caveat_is_shown_once(agent, fake):
    call = lambda state: (
        "run_metric",
        {"metric_name": "cancel_rate", "customer_state": [state]},
    )
    fake.script = [[call("SP")], [call("RJ")], "İptal oranları."]

    reply = ask(agent, "SP ve RJ iptal oranları?")

    assert len(reply.queries) == 2
    assert len(reply.caveats) == 1


def test_ranking_is_done_by_the_tool_not_by_the_model(agent, fake):
    fake.script = [
        [
            (
                "run_metric",
                {
                    "metric_name": "order_count",
                    "group_by": ["customer_state"],
                    "min_count": 2,
                    "order": "value_desc",
                    "top": 5,
                },
            )
        ],
        "SP: 29.",
    ]

    reply = ask(agent, "En az 2 siparişi olan eyaletler, çoktan aza?")

    assert tool_results(fake)[0]["rows"] == [["SP", 29, 29]]
    assert "WHERE numerator >= :min_count ORDER BY value DESC" in reply.queries[0]
    assert reply.queries[0].endswith("LIMIT 5")


# --- Free SQL -------------------------------------------------------------


def test_sql_answer_carries_the_sql_that_ran(agent, fake):
    fake.script = [[("run_sql", {"query": GOOD_SQL})], "Durumlara göre sayılar."]

    reply = ask(agent, "Durumlara göre sipariş sayısı?")

    assert reply.queries == [GOOD_SQL + " LIMIT 1000"]
    assert reply.caveats == []
    assert ["delivered", 22] in tool_results(fake)[0]["rows"]


def test_query_corrected_on_the_second_try_gives_a_normal_answer(agent, fake):
    fake.script = [
        [("run_sql", {"query": BAD_SQL})],
        [("run_sql", {"query": "SELECT customer_state FROM v_orders LIMIT 1"})],
        "SP.",
    ]

    reply = ask(agent, "Müşteriler nerede?")

    results = tool_results(fake)
    assert results[0]["error"] == "SQL_ERROR"
    assert results[0]["corrections_left"] == 2
    assert results[1]["rows"] == [["SP"]]
    assert reply.gave_up is False
    assert reply.text == "SP."
    # Only the query that worked is shown as the source.
    assert reply.queries == ["SELECT customer_state FROM v_orders LIMIT 1"]


def test_wrong_column_three_times_ends_in_could_not_answer(agent, fake):
    attempts = [
        "SELECT customer_city FROM v_orders",
        "SELECT city FROM v_orders",
        "SELECT o.customer_city FROM v_orders AS o",
    ]
    fake.script = [
        *([("run_sql", {"query": query})] for query in attempts),
        "Şehirlere göre dağılım şöyle: Sao Paulo en çok.",
    ]

    reply = ask(agent, "Şehirlere göre müşteri dağılımı?")

    assert reply.gave_up is True
    # The model's made-up answer is not what the person sees, and no rows.
    assert reply.text == messages.SQL_GAVE_UP
    assert reply.table is None
    assert reply.queries == [query + " LIMIT 1000" for query in attempts]
    assert reply.display == (
        f"{messages.SQL_GAVE_UP}\n\n{messages.OPS_TRIED_SQL_HEADING}\n"
        + "\n".join(reply.queries)
    )
    assert [result["corrections_left"] for result in tool_results(fake)] == [2, 1, 0]


def test_fourth_query_is_not_run(agent, fake, synthetic_db_path):
    fake.script = [
        *(
            [("run_sql", {"query": f"SELECT missing_{n} FROM v_orders"})]
            for n in range(3)
        ),
        [("run_sql", {"query": GOOD_SQL})],
        "Sonunda buldum.",
    ]

    reply = ask(agent, "Bir şey bul.")

    results = tool_results(fake)
    assert results[3]["error"] == "SQL_CORRECTION_LIMIT"
    assert "rows" not in results[3]
    assert reply.gave_up is True
    assert len(reply.queries) == 3


def test_validator_refusals_count_as_failed_attempts(agent, fake):
    fake.script = [
        [("run_sql", {"query": "SELECT * FROM customers"})],
        [("run_sql", {"query": "DROP TABLE orders"})],
        [("run_sql", {"query": "SELECT * FROM orders"})],
        "Olmadı.",
    ]

    reply = ask(agent, "Ham tabloları göster.")

    assert [result["error"] for result in tool_results(fake)] == ["SQL_REJECTED"] * 3
    assert reply.gave_up is True
    # A refused query has no rewritten form: the text the model sent is shown.
    assert reply.queries == [
        "SELECT * FROM customers",
        "DROP TABLE orders",
        "SELECT * FROM orders",
    ]


def test_metric_found_after_the_limit_is_a_real_answer(agent, fake):
    fake.script = [
        *(
            [("run_sql", {"query": f"SELECT missing_{n} FROM v_orders"})]
            for n in range(3)
        ),
        [("run_metric", {"metric_name": "order_count"})],
        "29 sipariş var.",
    ]

    reply = ask(agent, "Kaç sipariş var?")

    assert reply.gave_up is False
    assert reply.text == "29 sipariş var."
    assert len(reply.queries) == 1


def test_correction_count_starts_again_with_the_next_question(agent, fake):
    fake.script = [
        *(
            [("run_sql", {"query": f"SELECT missing_{n} FROM v_orders"})]
            for n in range(3)
        ),
        "Olmadı.",
        [("run_sql", {"query": GOOD_SQL})],
        "Durumlara göre sayılar.",
    ]

    reply = ask(agent, "İlk soru.", "İkinci soru.")

    assert reply.gave_up is False
    assert reply.queries == [GOOD_SQL + " LIMIT 1000"]


# --- Read-only, and nothing personal ---------------------------------------


def test_attacks_change_nothing(agent, fake, synthetic_db_path):
    before = file_hash(synthetic_db_path)
    fake.script = [
        [("run_sql", {"query": "'; DROP TABLE orders; --"})],
        [("run_sql", {"query": "SELECT 1; DELETE FROM return_requests"})],
        [("run_sql", {"query": "ATTACH DATABASE 'x.db' AS x"})],
        "Çalıştırılamadı.",
    ]

    reply = ask(agent, "'; DROP TABLE orders; --")

    assert reply.gave_up is True
    assert file_hash(synthetic_db_path) == before
    assert not (synthetic_db_path.parent / "x.db").exists()


def test_metric_connection_cannot_write(agent):
    with pytest.raises(Exception, match="readonly"):
        agent._conn.execute("DELETE FROM return_requests")


def test_model_is_reached_through_the_guard(agent, fake):
    raw_id = "0a1b2c3d4e5f60718293a4b5c6d7e8f9"
    fake.script = ["Bu veriye erişemem."]

    ask(agent, f"{raw_id} siparişini ve ayse@example.com müşterisini bul.")

    sent = fake.sent_text()
    assert raw_id not in sent
    assert "ayse@example.com" not in sent
    assert "[id] siparişini ve [email] müşterisini bul." in sent


def test_nothing_personal_reaches_the_model_from_the_views(agent, fake):
    fake.script = [
        [("run_sql", {"query": "SELECT * FROM v_orders"})],
        [("run_sql", {"query": "SELECT * FROM v_order_items"})],
        "Tamam.",
    ]

    ask(agent, "Bütün satırları göster.")

    sent = fake.sent_text()
    assert re.search(r"[0-9a-f]{32}", sent) is None
    for forbidden in ("sao paulo", "01310", "u_alice", "o_day", "c_o_"):
        assert forbidden not in sent


# --- Long results -----------------------------------------------------------


def test_long_result_is_cut_for_the_model():
    result = {"columns": ["n"], "rows": [[n] for n in range(MAX_ROWS_FOR_MODEL + 50)]}

    cut = cut_rows(result)

    assert len(cut["rows"]) == MAX_ROWS_FOR_MODEL
    assert cut["rows_not_shown"] == 50
    assert len(result["rows"]) == MAX_ROWS_FOR_MODEL + 50  # the original is untouched


def test_short_result_and_errors_are_left_alone():
    assert cut_rows({"rows": [[1]]}) == {"rows": [[1]]}
    assert cut_rows({"error": "SQL_ERROR"}) == {"error": "SQL_ERROR"}


# --- Loop limits ------------------------------------------------------------


def test_third_identical_call_is_not_run(agent, fake):
    call = ("run_metric", {"metric_name": "order_count"})
    fake.script = [[call], [call], [call], "29."]

    ask(agent, "Kaç sipariş?")

    assert [result.get("error") for result in tool_results(fake)] == [
        None,
        None,
        "REPEATED_CALL",
    ]


def test_run_stops_at_the_step_limit(agent, fake):
    fake.script = [
        [
            (
                "run_metric",
                {"metric_name": "order_count", "customer_state": [str(n)]},
            )
        ]
        for n in range(30)
    ]

    reply = ask(agent, "Her eyalet için tek tek say.")

    assert reply.text == messages.STEP_LIMIT_REACHED
    assert reply.log.stopped_at_step_limit is True
