"""Tests for read-only free SQL, on the synthetic database."""

import hashlib
import json
import re
import sqlite3

import pytest

from src.knowledge.semantic_layer import run_metric
from src.knowledge.sql_runner import connect_read_only, run_sql
from tests.synthetic_data import ALICE, BOB

ATTACKS = [
    "DROP TABLE orders",
    "SELECT * FROM v_orders; DROP TABLE orders",
    "'; DROP TABLE orders; --",
    "SELECT 1; DELETE FROM return_requests",
    "ATTACH DATABASE 'attached.db' AS other",
    "SELECT 1; ATTACH DATABASE 'attached.db' AS other",
    "PRAGMA writable_schema = ON",
    "PRAGMA table_info(customers)",
    "UPDATE orders SET order_status = 'canceled'",
    (
        "INSERT INTO return_requests (order_id, customer_unique_id, refund_amount, "
        "status, created_at) VALUES ('x', 'y', 1, 'APPROVED', '2018-09-01')"
    ),
    "VACUUM INTO 'copy.db'",
    "CREATE TABLE loot AS SELECT * FROM customers",
    "WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone",
]


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Queries that run ---------------------------------------------------


def test_count_over_a_view(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT COUNT(*) AS orders FROM v_orders")

    assert answer == {
        "columns": ["orders"],
        "rows": [[29]],
        "sql": "SELECT COUNT(*) AS orders FROM v_orders LIMIT 1000",
    }


def test_number_of_customers_through_the_views(synthetic_db_path):
    answer = run_sql(
        synthetic_db_path, "SELECT COUNT(DISTINCT customer_key) FROM v_orders"
    )

    # Alice and Bob.
    assert answer["rows"] == [[2]]


def test_gmv_by_state_matches_the_metric(synthetic_db_path, synthetic_db):
    answer = run_sql(
        synthetic_db_path,
        "SELECT o.customer_state, SUM(i.price) AS gmv "
        "FROM v_orders AS o JOIN v_order_items AS i ON i.order_key = o.order_key "
        "WHERE o.order_status NOT IN ('canceled', 'unavailable') "
        "GROUP BY o.customer_state",
    )
    metric = run_metric(synthetic_db, "gmv", group_by=["customer_state"])

    assert answer["columns"] == ["customer_state", "gmv"]
    assert answer["rows"] == [["SP", pytest.approx(3670.01)]]
    assert answer["rows"][0][1] == pytest.approx(metric["rows"][0][-1])


def test_late_delivery_rate_matches_the_metric(synthetic_db_path, synthetic_db):
    answer = run_sql(
        synthetic_db_path,
        "SELECT AVG(DATE(order_delivered_customer_date) > "
        "DATE(order_estimated_delivery_date)) FROM v_orders "
        "WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL "
        "AND DATE(order_delivered_customer_date) <= '2018-09-01'",
    )
    metric = run_metric(synthetic_db, "late_delivery_rate")

    assert answer["rows"][0][0] == pytest.approx(metric["rows"][0][-1]) == 0.25


def test_rows_are_cut_at_the_limit(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT order_key FROM v_orders", max_rows=10)

    assert len(answer["rows"]) == 10
    assert answer["sql"].endswith("LIMIT 10")


def test_larger_limit_is_lowered(synthetic_db_path):
    answer = run_sql(
        synthetic_db_path, "SELECT order_key FROM v_orders LIMIT 5000", max_rows=10
    )

    assert len(answer["rows"]) == 10


# --- Queries that are refused -------------------------------------------


def test_raw_table_is_refused_with_the_allowed_views(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT * FROM customers")

    assert answer["error"] == "SQL_REJECTED"
    assert answer["reason"] == "TABLE_NOT_ALLOWED"
    assert answer["detail"] == "customers"
    assert "v_orders" in answer["message"]
    assert "rows" not in answer


@pytest.mark.parametrize(
    "column",
    ["customer_city", "customer_zip_code_prefix", "customer_unique_id", "order_id"],
)
def test_column_that_is_not_in_a_view_cannot_be_read(synthetic_db_path, column):
    answer = run_sql(synthetic_db_path, f"SELECT {column} FROM v_orders")

    assert answer["error"] == "SQL_ERROR"
    assert column in answer["detail"]
    assert "rows" not in answer


def test_review_text_cannot_be_read(synthetic_db_path):
    answer = run_sql(
        synthetic_db_path, "SELECT review_comment_message FROM v_order_reviews"
    )

    assert answer["error"] == "SQL_ERROR"


def test_view_definitions_cannot_be_read(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT sql FROM sqlite_master")

    assert answer["reason"] == "TABLE_NOT_ALLOWED"


def test_cte_named_like_a_real_table_is_refused(synthetic_db_path):
    # The names come from the database itself, not from a list in the code.
    answer = run_sql(
        synthetic_db_path,
        "SELECT * FROM geolocation WHERE 1 IN "
        "(WITH geolocation AS (SELECT 1 AS x) SELECT x FROM geolocation)",
    )

    assert answer["reason"] == "TABLE_NOT_ALLOWED"


def test_query_with_a_placeholder_fails_cleanly(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT * FROM v_orders WHERE order_key = ?")

    assert answer["error"] == "SQL_ERROR"


def test_outputs_hold_no_raw_id_or_place(synthetic_db_path):
    answers = [
        run_sql(synthetic_db_path, f"SELECT * FROM {view}")
        for view in (
            "v_orders",
            "v_order_items",
            "v_order_payments",
            "v_order_reviews",
            "v_return_requests",
        )
    ]
    text = json.dumps(answers)

    assert all("rows" in answer for answer in answers)
    assert re.search(r"[0-9a-f]{32}", text) is None
    for forbidden in (ALICE, BOB, "o_day", "c_o_", "sao paulo", "01310"):
        assert forbidden not in text


# --- Attacks leave the database as it was -------------------------------


@pytest.mark.parametrize("attack", ATTACKS)
def test_attack_is_refused_and_the_database_is_unchanged(synthetic_db_path, attack):
    before = file_hash(synthetic_db_path)
    files_before = sorted(path.name for path in synthetic_db_path.parent.iterdir())

    answer = run_sql(synthetic_db_path, attack)

    assert answer["error"] == "SQL_REJECTED"
    assert "rows" not in answer
    assert file_hash(synthetic_db_path) == before
    assert (
        sorted(path.name for path in synthetic_db_path.parent.iterdir()) == files_before
    )


def test_database_is_unchanged_after_ordinary_queries(synthetic_db_path):
    before = file_hash(synthetic_db_path)

    run_sql(synthetic_db_path, "SELECT * FROM v_orders")
    run_sql(synthetic_db_path, "SELECT COUNT(*) FROM v_order_items")

    assert file_hash(synthetic_db_path) == before


# --- The connection itself, with the validator out of the way -----------


def test_connection_refuses_writes(synthetic_db_path):
    conn = connect_read_only(synthetic_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM return_requests")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DROP TABLE orders")
    finally:
        conn.close()


def test_connection_refuses_attach_and_creates_no_file(synthetic_db_path):
    target = synthetic_db_path.parent / "attached.db"
    conn = connect_read_only(synthetic_db_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="too many attached"):
            conn.execute(f"ATTACH DATABASE '{target.as_posix()}' AS other")
    finally:
        conn.close()

    assert not target.exists()


def test_without_the_attach_limit_a_read_only_connection_creates_a_file(
    synthetic_db_path,
):
    # Why the limit is needed: mode=ro alone does not stop ATTACH.
    target = synthetic_db_path.parent / "attached.db"
    conn = sqlite3.connect(f"file:{synthetic_db_path.as_posix()}?mode=ro", uri=True)
    try:
        conn.execute(f"ATTACH DATABASE '{target.as_posix()}' AS other")
        conn.execute("CREATE TABLE other.loot (x)")
    finally:
        conn.close()

    assert target.exists()


# --- Time limit ---------------------------------------------------------


def test_query_that_runs_too_long_is_stopped(synthetic_db_path):
    endless = (
        "WITH RECURSIVE counter(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM counter) "
        "SELECT COUNT(*) FROM counter"
    )

    answer = run_sql(synthetic_db_path, endless, timeout_seconds=0.2)

    assert answer["error"] == "SQL_TIMEOUT"
    assert "rows" not in answer


def test_quick_query_is_not_stopped(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT COUNT(*) FROM v_orders")

    assert answer["rows"] == [[29]]
