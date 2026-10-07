"""Tests for scripts/load_sqlite.py, on tiny synthetic CSV files.

No Olist data is used: each test builds its own raw folder in tmp_path.
"""

import csv
import sqlite3
from datetime import date

import pytest

from scripts import load_sqlite

SIMULATED_TODAY = date(2018, 9, 1)

# o1: the day before the simulated today, kept.
# o2: purchased at midnight on the simulated today, left out by R0.
# o3: kept, not delivered yet (empty delivery dates).
ROWS = {
    "orders": [
        {
            "order_id": "o1",
            "customer_id": "c1",
            "order_status": "delivered",
            "order_purchase_timestamp": "2018-08-31 23:59:59",
            "order_delivered_customer_date": "2018-09-05 10:00:00",
        },
        {
            "order_id": "o2",
            "customer_id": "c2",
            "order_status": "canceled",
            "order_purchase_timestamp": "2018-09-01 00:00:00",
        },
        {
            "order_id": "o3",
            "customer_id": "c3",
            "order_status": "shipped",
            "order_purchase_timestamp": "2018-08-20 08:00:00",
        },
    ],
    "customers": [
        {
            "customer_id": "c1",
            "customer_unique_id": "u1",
            "customer_zip_code_prefix": "01037",
        },
        {
            "customer_id": "c2",
            "customer_unique_id": "u2",
            "customer_zip_code_prefix": "20000",
        },
        {
            "customer_id": "c3",
            "customer_unique_id": "u1",
            "customer_zip_code_prefix": "01037",
        },
    ],
    "order_items": [
        {"order_id": "o1", "order_item_id": "1", "product_id": "p1", "price": "58.90"},
        {"order_id": "o1", "order_item_id": "2", "product_id": "p2", "price": "10"},
        {"order_id": "o2", "order_item_id": "1", "product_id": "p1", "price": "58.90"},
    ],
    "order_payments": [
        {"order_id": "o1", "payment_sequential": "1", "payment_value": "68.90"},
        {"order_id": "o2", "payment_sequential": "1", "payment_value": "58.90"},
    ],
    "order_reviews": [
        {"review_id": "r1", "order_id": "o1", "review_score": "5"},
        # The same review_id twice, as in the real data.
        {"review_id": "r1", "order_id": "o3", "review_score": "5"},
        {"review_id": "r2", "order_id": "o2", "review_score": "1"},
    ],
    "products": [
        {
            "product_id": "p1",
            "product_category_name": "perfumaria",
            "product_weight_g": "225",
        },
        {"product_id": "p2"},
    ],
    "sellers": [{"seller_id": "s1", "seller_zip_code_prefix": "09350"}],
    "geolocation": [
        {"geolocation_zip_code_prefix": "01037", "geolocation_lat": "-23.5"}
    ],
    "product_category_name_translation": [
        {
            "product_category_name": "perfumaria",
            "product_category_name_english": "perfumery",
        }
    ],
}


def write_raw(raw_dir, rows=ROWS):
    """Write one CSV per table; columns a row does not mention stay empty."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for table in load_sqlite.TABLES:
        with (raw_dir / table.csv_file).open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(table.columns), restval="")
            writer.writeheader()
            writer.writerows(rows[table.name])
    return raw_dir


@pytest.fixture
def raw_dir(tmp_path):
    return write_raw(tmp_path / "raw")


@pytest.fixture
def db(raw_dir, tmp_path):
    db_path = tmp_path / "marketdesk.db"
    load_sqlite.build_database(raw_dir, db_path, SIMULATED_TODAY)
    conn = sqlite3.connect(db_path)
    yield conn
    conn.close()


def column(conn, sql):
    return [row[0] for row in conn.execute(sql)]


def test_r0_leaves_out_orders_purchased_on_or_after_simulated_today(db):
    assert column(db, "SELECT order_id FROM orders ORDER BY order_id") == ["o1", "o3"]


@pytest.mark.parametrize(
    ("timestamp", "excluded"),
    [
        ("2018-08-31 23:59:59", False),
        ("2018-09-01 00:00:00", True),
        ("2018-09-01 23:59:59", True),
        ("2018-10-17 17:30:18", True),
        (None, False),
    ],
)
def test_r0_compares_calendar_days(timestamp, excluded):
    assert load_sqlite.is_excluded_by_r0(timestamp, SIMULATED_TODAY) is excluded


def test_r0_also_leaves_out_rows_that_belong_to_an_excluded_order(db):
    assert column(db, "SELECT DISTINCT order_id FROM order_items") == ["o1"]
    assert column(db, "SELECT order_id FROM order_payments") == ["o1"]
    assert column(db, "SELECT order_id FROM order_reviews ORDER BY order_id") == [
        "o1",
        "o3",
    ]
    assert column(db, "SELECT customer_id FROM customers ORDER BY customer_id") == [
        "c1",
        "c3",
    ]


def test_build_reports_row_counts_and_excluded_orders(raw_dir, tmp_path):
    counts = load_sqlite.build_database(raw_dir, tmp_path / "x.db", SIMULATED_TODAY)

    assert counts["orders"] == 2
    assert counts["order_items"] == 2
    assert counts["customers"] == 2
    assert counts["products"] == 2
    assert counts["return_requests"] == 0
    assert counts["excluded_by_r0"] == 1


def test_empty_cells_are_loaded_as_null_not_empty_string(db):
    delivered = db.execute(
        "SELECT order_delivered_customer_date FROM orders WHERE order_id = 'o3'"
    ).fetchone()[0]
    category = db.execute(
        "SELECT product_category_name FROM products WHERE product_id = 'p2'"
    ).fetchone()[0]

    assert delivered is None
    assert category is None
    for table in load_sqlite.TABLES:
        for name in table.columns:
            empty = db.execute(
                f"SELECT COUNT(*) FROM {table.name} WHERE {name} = ''"
            ).fetchone()[0]
            assert empty == 0, f"{table.name}.{name} holds empty strings"


def test_columns_get_their_declared_types(db):
    types = db.execute(
        "SELECT typeof(order_item_id), typeof(price) FROM order_items WHERE price = 10"
    ).fetchone()
    score_type = db.execute(
        "SELECT typeof(review_score) FROM order_reviews"
    ).fetchone()[0]

    assert types == ("integer", "real")
    assert score_type == "integer"


def test_zip_code_prefix_keeps_its_leading_zero(db):
    prefixes = column(
        db, "SELECT customer_zip_code_prefix FROM customers WHERE customer_id = 'c1'"
    )

    assert prefixes == ["01037"]


def test_return_requests_table_exists_and_is_empty(db):
    columns = [row[1] for row in db.execute("PRAGMA table_info(return_requests)")]

    assert columns == [
        "id",
        "order_id",
        "customer_unique_id",
        "reason",
        "status",
        "created_at",
    ]
    assert db.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0] == 0


def test_indexes_are_created(db):
    names = set(column(db, "SELECT name FROM sqlite_master WHERE type = 'index'"))

    for table_name, column_name in load_sqlite.INDEXES:
        assert f"idx_{table_name}_{column_name}" in names


def test_rebuild_replaces_the_existing_database(raw_dir, tmp_path):
    db_path = tmp_path / "marketdesk.db"
    load_sqlite.build_database(raw_dir, db_path, SIMULATED_TODAY)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO return_requests (order_id, customer_unique_id, status, created_at) "
        "VALUES ('o1', 'u1', 'PENDING_REVIEW', '2018-09-01')"
    )
    conn.commit()
    conn.close()

    counts = load_sqlite.build_database(raw_dir, db_path, SIMULATED_TODAY)

    conn = sqlite3.connect(db_path)
    try:
        assert counts["orders"] == 2
        assert conn.execute("SELECT COUNT(*) FROM return_requests").fetchone()[0] == 0
    finally:
        conn.close()


def test_unexpected_csv_columns_stop_the_build_and_leave_no_database(tmp_path):
    raw_dir = write_raw(tmp_path / "raw")
    (raw_dir / "olist_sellers_dataset.csv").write_text("seller_id,unexpected\ns1,x\n")
    db_path = tmp_path / "marketdesk.db"

    with pytest.raises(ValueError, match="olist_sellers_dataset.csv"):
        load_sqlite.build_database(raw_dir, db_path, SIMULATED_TODAY)

    assert not db_path.exists()
    assert not (tmp_path / "marketdesk.db.tmp").exists()


def test_failed_rebuild_keeps_the_previous_database(raw_dir, tmp_path):
    db_path = tmp_path / "marketdesk.db"
    load_sqlite.build_database(raw_dir, db_path, SIMULATED_TODAY)
    (raw_dir / "olist_sellers_dataset.csv").write_text("seller_id,unexpected\ns1,x\n")

    with pytest.raises(ValueError):
        load_sqlite.build_database(raw_dir, db_path, SIMULATED_TODAY)

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 2
    finally:
        conn.close()
