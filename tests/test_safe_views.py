"""Tests for the safe views, on the synthetic database."""

import re

import pytest

from src.knowledge.safe_views import ALLOWED_VIEWS, SAFE_VIEWS, create_view_statements
from tests.synthetic_data import ALICE, BOB

# Column names a view must never show, whole or as part of a name.
FORBIDDEN_COLUMN_PARTS = (
    "order_id",
    "customer_id",
    "customer_unique_id",
    "product_id",
    "seller_id",
    "review_id",
    "city",
    "zip",
    "lat",
    "lng",
    "comment",
)


def columns_of(conn, view):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({view})")]


def test_database_holds_only_the_safe_views(synthetic_db):
    views = [
        row[0]
        for row in synthetic_db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name"
        )
    ]

    assert views == sorted(ALLOWED_VIEWS)
    assert len(create_view_statements()) == len(SAFE_VIEWS) == 5


@pytest.mark.parametrize("view", ALLOWED_VIEWS)
def test_views_hide_id_city_zip_review(synthetic_db, view):
    columns = columns_of(synthetic_db, view)

    assert columns
    for column in columns:
        for part in FORBIDDEN_COLUMN_PARTS:
            assert part not in column


@pytest.mark.parametrize("view", ALLOWED_VIEWS)
def test_view_rows_hold_no_raw_id_or_place(synthetic_db, view):
    # Give the raw rows values shaped like the real ones, then read the view.
    synthetic_db.executescript(
        """
        UPDATE customers SET customer_city = 'campinas',
            customer_zip_code_prefix = '13010';
        UPDATE order_reviews SET review_comment_title = 'titulo secreto',
            review_comment_message = 'mensagem secreta';
        """
    )

    text = repr(synthetic_db.execute(f"SELECT * FROM {view}").fetchall())

    assert re.search(r"[0-9a-f]{32}", text) is None
    for forbidden in (ALICE, BOB, "o_day", "c_o_", "p_chair", "s_main", "campinas"):
        assert forbidden not in text
    assert "13010" not in text
    assert "secret" not in text


def test_each_order_appears_once(synthetic_db):
    orders, keys = synthetic_db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT order_key) FROM v_orders"
    ).fetchone()

    assert orders == keys == 29


def test_customer_key_is_one_per_person(synthetic_db):
    # Alice has 28 orders, Bob has one: two people, two keys.
    counts = dict(
        synthetic_db.execute(
            "SELECT customer_key, COUNT(*) FROM v_orders GROUP BY customer_key"
        ).fetchall()
    )

    assert sorted(counts.values()) == [1, 28]


def test_views_join_on_the_order_key(synthetic_db):
    rows = synthetic_db.execute(
        "SELECT o.order_status, COUNT(*), SUM(i.price) "
        "FROM v_orders AS o JOIN v_order_items AS i ON i.order_key = o.order_key "
        "WHERE i.price = 50.0 OR i.price = 40.0 GROUP BY o.order_status"
    ).fetchall()

    # The second items of o_two_items (50.00) and o_seller_late_one_item (40.00).
    assert [tuple(row) for row in rows] == [("delivered", 2, 90.0)]


def test_views_keep_their_row_counts(synthetic_db):
    for view, table in (
        ("v_order_items", "order_items"),
        ("v_order_payments", "order_payments"),
        ("v_order_reviews", "order_reviews"),
        ("v_return_requests", "return_requests"),
    ):
        in_view = synthetic_db.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
        in_table = synthetic_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        assert in_view == in_table > 0


def test_item_view_shows_category_and_state(synthetic_db):
    row = synthetic_db.execute(
        "SELECT product_category_en, seller_state, price, freight_value "
        "FROM v_order_items LIMIT 1"
    ).fetchone()

    assert tuple(row) == ("furniture_decor", "SP", 100.0, 15.0)


def test_request_view_links_to_order(synthetic_db):
    rows = synthetic_db.execute(
        "SELECT rr.status, o.order_status FROM v_return_requests AS rr "
        "JOIN v_orders AS o ON o.order_key = rr.order_key ORDER BY rr.status"
    ).fetchall()

    assert [tuple(row) for row in rows] == [
        ("PENDING_REVIEW", "delivered"),
        ("REJECTED", "delivered"),
    ]
