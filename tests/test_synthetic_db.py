"""Checks that the synthetic database really holds the cases it promises.

These tests read raw facts (dates, amounts, statuses), not rule decisions:
the rule engine has its own tests. If someone edits synthetic_data.py and
breaks a boundary case, the failure shows up here first.
"""

import pytest

import config
from tests import synthetic_data
from tests.synthetic_data import ALICE, BOB

TODAY = config.SIMULATED_TODAY.isoformat()


def value(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


def days_since_delivery(conn, order_id):
    return value(
        conn,
        "SELECT CAST(julianday(DATE(?)) - "
        "julianday(DATE(order_delivered_customer_date)) AS INTEGER) "
        "FROM orders WHERE order_id = ?",
        TODAY,
        order_id,
    )


def days_late(conn, order_id):
    return value(
        conn,
        "SELECT CAST(julianday(DATE(order_delivered_customer_date)) - "
        "julianday(DATE(order_estimated_delivery_date)) AS INTEGER) "
        "FROM orders WHERE order_id = ?",
        order_id,
    )


def test_database_holds_between_20_and_30_orders(synthetic_db):
    count = value(synthetic_db, "SELECT COUNT(*) FROM orders")

    # One order of synthetic_data.ORDERS is left out by R0.
    assert count == len(synthetic_data.ORDERS) - 1
    assert 20 <= count <= 30


def test_order_purchased_on_simulated_today_is_not_loaded(synthetic_db):
    assert (
        value(
            synthetic_db,
            "SELECT COUNT(*) FROM orders WHERE order_id = 'o_purchased_today'",
        )
        == 0
    )
    assert (
        value(
            synthetic_db,
            "SELECT COUNT(*) FROM orders WHERE DATE(order_purchase_timestamp) >= DATE(?)",
            TODAY,
        )
        == 0
    )


def test_one_order_belongs_to_another_customer(synthetic_db):
    owners = dict(
        synthetic_db.execute(
            "SELECT customers.customer_unique_id, COUNT(*) FROM orders "
            "JOIN customers USING (customer_id) GROUP BY 1"
        ).fetchall()
    )

    assert owners[BOB] == 1
    assert owners[ALICE] == len(synthetic_data.ORDERS) - 2
    assert (
        value(
            synthetic_db,
            "SELECT customer_unique_id FROM orders JOIN customers USING (customer_id) "
            "WHERE order_id = 'o_other_customer'",
        )
        == BOB
    )


@pytest.mark.parametrize(
    ("order_id", "status"),
    [
        ("o_created", "created"),
        ("o_approved", "approved"),
        ("o_invoiced", "invoiced"),
        ("o_processing", "processing"),
        ("o_shipped", "shipped"),
        ("o_canceled", "canceled"),
        ("o_unavailable", "unavailable"),
    ],
)
def test_every_non_delivered_status_has_an_order(synthetic_db, order_id, status):
    row = synthetic_db.execute(
        "SELECT order_status, order_delivered_customer_date FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()

    assert row["order_status"] == status
    assert row["order_delivered_customer_date"] is None


def test_delivered_order_with_a_future_delivery_date(synthetic_db):
    assert (
        value(
            synthetic_db,
            "SELECT order_status FROM orders WHERE order_id = 'o_delivered_future'",
        )
        == "delivered"
    )
    assert days_since_delivery(synthetic_db, "o_delivered_future") == -4


def test_delivered_order_without_a_delivery_date(synthetic_db):
    row = synthetic_db.execute(
        "SELECT order_status, order_delivered_customer_date FROM orders "
        "WHERE order_id = 'o_no_delivery_date'"
    ).fetchone()

    assert row["order_status"] == "delivered"
    assert row["order_delivered_customer_date"] is None


@pytest.mark.parametrize(
    ("order_id", "days"),
    [("o_day0", 0), ("o_day14", 14), ("o_day15", 15), ("o_day30", 30), ("o_day31", 31)],
)
def test_window_boundary_orders_are_the_promised_number_of_days_old(
    synthetic_db, order_id, days
):
    assert days_since_delivery(synthetic_db, order_id) == days


@pytest.mark.parametrize(
    ("order_id", "late", "age"),
    [
        ("o_late_10", 10, 7),
        ("o_late_9", 9, 7),
        ("o_late_freight_only", 16, 22),
        ("o_late_day30", 13, 30),
        ("o_late_day31", 15, 31),
    ],
)
def test_late_orders(synthetic_db, order_id, late, age):
    assert days_late(synthetic_db, order_id) == late
    assert days_since_delivery(synthetic_db, order_id) == age


def test_on_time_orders_are_not_late(synthetic_db):
    assert days_late(synthetic_db, "o_day14") < 0


@pytest.mark.parametrize(
    ("order_id", "price", "freight"),
    [
        ("o_two_items", 150.00, 15.00),
        ("o_amount_500", 500.00, 20.00),
        ("o_amount_over", 500.01, 20.00),
        ("o_voucher", 180.00, 20.00),
        ("o_day14", 100.00, 15.00),
    ],
)
def test_item_totals(synthetic_db, order_id, price, freight):
    row = synthetic_db.execute(
        "SELECT ROUND(SUM(price), 2), ROUND(SUM(freight_value), 2) FROM order_items "
        "WHERE order_id = ?",
        (order_id,),
    ).fetchone()

    assert tuple(row) == (price, freight)


def test_two_item_order_has_two_items(synthetic_db):
    assert (
        value(
            synthetic_db,
            "SELECT COUNT(*) FROM order_items WHERE order_id = 'o_two_items'",
        )
        == 2
    )


def test_voucher_order_is_one_quarter_voucher(synthetic_db):
    voucher = value(
        synthetic_db,
        "SELECT SUM(payment_value) FROM order_payments "
        "WHERE order_id = 'o_voucher' AND payment_type = 'voucher'",
    )
    total = value(
        synthetic_db,
        "SELECT SUM(payment_value) FROM order_payments WHERE order_id = 'o_voucher'",
    )

    assert voucher / total == 0.25


def test_payments_cover_items_and_freight(synthetic_db):
    mismatched = synthetic_db.execute(
        "SELECT o.order_id FROM orders o "
        "JOIN (SELECT order_id, ROUND(SUM(price + freight_value), 2) AS due "
        "      FROM order_items GROUP BY order_id) i USING (order_id) "
        "JOIN (SELECT order_id, ROUND(SUM(payment_value), 2) AS paid "
        "      FROM order_payments GROUP BY order_id) p USING (order_id) "
        "WHERE i.due != p.paid"
    ).fetchall()

    assert mismatched == []


def orders_handed_over_after_the_limit(conn):
    """Orders where any item's limit day is before the carrier day."""
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT o.order_id FROM orders o "
            "JOIN order_items i USING (order_id) "
            "WHERE DATE(o.order_delivered_carrier_date) > DATE(i.shipping_limit_date) "
            "ORDER BY o.order_id"
        )
    ]


def test_orders_handed_to_the_carrier_after_the_limit(synthetic_db):
    assert orders_handed_over_after_the_limit(synthetic_db) == [
        "o_seller_late",
        "o_seller_late_one_item",
    ]


def test_only_one_item_of_the_two_item_order_missed_its_limit(synthetic_db):
    late_items = [
        row[0]
        for row in synthetic_db.execute(
            "SELECT i.order_item_id FROM orders o JOIN order_items i USING (order_id) "
            "WHERE o.order_id = 'o_seller_late_one_item' "
            "AND DATE(o.order_delivered_carrier_date) > DATE(i.shipping_limit_date)"
        )
    ]

    assert late_items == [2]


def test_same_day_handover_is_later_by_the_clock_but_not_by_the_calendar(synthetic_db):
    row = synthetic_db.execute(
        "SELECT o.order_delivered_carrier_date > i.shipping_limit_date, "
        "DATE(o.order_delivered_carrier_date) > DATE(i.shipping_limit_date) "
        "FROM orders o JOIN order_items i USING (order_id) "
        "WHERE o.order_id = 'o_seller_same_day'"
    ).fetchone()

    assert tuple(row) == (1, 0)


def test_existing_return_requests(synthetic_db):
    requests = dict(
        synthetic_db.execute("SELECT order_id, status FROM return_requests").fetchall()
    )

    assert requests == {"o_duplicate": "PENDING_REVIEW", "o_duplicate_old": "REJECTED"}
    assert (
        days_since_delivery(synthetic_db, "o_duplicate")
        <= config.RETURN_WINDOW_SHORT_DAYS
    )
    assert (
        days_since_delivery(synthetic_db, "o_duplicate_old")
        > config.RETURN_WINDOW_LONG_DAYS
    )


def test_each_test_gets_its_own_copy(synthetic_db_path, synthetic_db_template):
    assert synthetic_db_path != synthetic_db_template
