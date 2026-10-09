"""Tests for the semantic layer, on the synthetic database.

Expected values are worked out here from tests/synthetic_data.py, not by
running the metric's own SQL a second time.
"""

import sqlite3
from datetime import date, datetime

import pytest

from src.knowledge.semantic_layer import (
    METRICS_PATH,
    list_metrics,
    load_semantic_layer,
    parse_semantic_layer,
    run_metric,
)
from tests import synthetic_data

TODAY = date(2018, 9, 1)
REQUIRED_METRICS = {
    "order_count",
    "gmv",
    "avg_order_value",
    "cancel_rate",
    "late_delivery_rate",
    "avg_delivery_days",
    "avg_review_score",
    "seller_late_shipping_rate",
}

# Orders as they are in the database: without the one R0 leaves out.
ORDERS = [o for o in synthetic_data.ORDERS if o["id"] != "o_purchased_today"]
CLOSED = ("canceled", "unavailable")


def items_of(order):
    return order.get("items", synthetic_data.DEFAULT_ITEMS)


def delivered_by_today(order):
    return (
        order["status"] == "delivered"
        and order["delivered"] is not None
        and order["delivered"][:10] <= TODAY.isoformat()
    )


def single(conn, metric_name, **kwargs):
    """Run a metric without grouping and return its one row as a dict."""
    answer = run_metric(conn, metric_name, **kwargs)
    assert len(answer["rows"]) == 1
    return dict(zip(answer["columns"], answer["rows"][0], strict=True))


def grouped(conn, metric_name, group_by, **kwargs):
    """Run a metric with grouping and return {group: row as a dict}."""
    answer = run_metric(conn, metric_name, group_by=group_by, **kwargs)
    width = len(group_by)
    return {
        tuple(row[:width]) if width > 1 else row[0]: dict(
            zip(answer["columns"], row, strict=True)
        )
        for row in answer["rows"]
    }


@pytest.fixture
def varied_db(synthetic_db):
    """The synthetic database with a second state, category and seller.

    o_two_items gets one item of each category and seller; o_shipped and
    o_canceled move to another month; Bob moves to another state.
    """
    synthetic_db.executescript(
        """
        INSERT INTO products (product_id, product_category_name)
            VALUES ('p_lamp', 'iluminacao');
        INSERT INTO product_category_name_translation VALUES ('iluminacao', 'lighting');
        INSERT INTO sellers (seller_id, seller_city, seller_state)
            VALUES ('s_other', 'rio de janeiro', 'RJ');
        UPDATE order_items SET product_id = 'p_lamp', seller_id = 's_other'
            WHERE order_id = 'o_two_items' AND order_item_id = 2;
        UPDATE orders SET order_purchase_timestamp = '2018-07-10 10:00:00'
            WHERE order_id IN ('o_shipped', 'o_canceled');
        UPDATE customers SET customer_state = 'RJ'
            WHERE customer_unique_id = 'u_bob';
        """
    )
    return synthetic_db


# --- The definitions ----------------------------------------------------


def test_the_eight_required_metrics_are_defined():
    assert set(load_semantic_layer().metrics) == REQUIRED_METRICS


def test_every_metric_has_all_its_fields():
    for metric in load_semantic_layer().metrics.values():
        assert metric.description
        assert metric.grain in ("order", "item")
        assert metric.base_filter
        assert metric.numerator
        assert metric.dimensions
        assert metric.caveat


def test_gmv_caveat_says_it_is_not_revenue_or_profit():
    caveat = load_semantic_layer().metrics["gmv"].caveat

    assert "gelir" in caveat
    assert "kâr" in caveat


def test_rates_and_averages_say_they_are_observational():
    metrics = load_semantic_layer().metrics
    for name in REQUIRED_METRICS - {"order_count", "gmv", "avg_order_value"}:
        assert "nedensellik değildir" in metrics[name].caveat


def test_no_dimension_exposes_city_or_zip_code():
    text = METRICS_PATH.read_text(encoding="utf-8")

    assert "city" not in text
    assert "zip" not in text
    assert "customer_unique_id" not in text


def test_list_metrics_gives_name_description_and_dimensions():
    listed = list_metrics()

    assert {metric["name"] for metric in listed["metrics"]} == REQUIRED_METRICS
    for metric in listed["metrics"]:
        assert set(metric) == {"name", "description", "dimensions", "caveat"}
        assert set(metric["dimensions"]) <= set(listed["dimensions"])
    assert listed["period_filters"] == ["purchase_from", "purchase_to"]


@pytest.mark.parametrize(
    ("old", "new", "fault"),
    [
        ("grain: item", "grain: basket", "unknown grain"),
        ("join: order_totals", "join: payments", "unknown join"),
        ("dimensions: [customer_state, purchase_month]", "dimensions: [city]", "city"),
        ("level: item", "level: basket", "unknown level"),
        ('    numerator: "COUNT(*)"\n', "", "numerator"),
    ],
)
def test_faulty_definitions_are_refused_when_read(old, new, fault):
    text = METRICS_PATH.read_text(encoding="utf-8")
    assert old in text

    with pytest.raises(ValueError, match=fault):
        parse_semantic_layer(text.replace(old, new, 1))


# --- The eight metrics, without grouping --------------------------------


def test_order_count(synthetic_db):
    assert single(synthetic_db, "order_count")["value"] == len(ORDERS) == 29


def test_gmv_leaves_out_closed_orders_and_freight(synthetic_db):
    expected = sum(
        float(price)
        for order in ORDERS
        if order["status"] not in CLOSED
        for price, *_ in items_of(order)
    )

    assert single(synthetic_db, "gmv")["value"] == pytest.approx(expected)
    assert expected == pytest.approx(3670.01)


def test_avg_order_value_is_gmv_over_order_count(synthetic_db):
    row = single(synthetic_db, "avg_order_value")

    assert row["numerator"] == pytest.approx(single(synthetic_db, "gmv")["value"])
    assert row["denominator"] == single(synthetic_db, "order_count")["value"]
    assert row["value"] == pytest.approx(3670.01 / 29)


def test_cancel_rate_counts_canceled_but_not_unavailable(synthetic_db):
    row = single(synthetic_db, "cancel_rate")

    assert (row["numerator"], row["denominator"]) == (1, 29)
    assert row["value"] == pytest.approx(1 / 29)


def test_late_delivery_rate(synthetic_db):
    delivered = [order for order in ORDERS if delivered_by_today(order)]
    late = [o for o in delivered if o["delivered"][:10] > o["estimated"][:10]]

    row = single(synthetic_db, "late_delivery_rate")

    assert (row["numerator"], row["denominator"]) == (len(late), len(delivered))
    assert (len(late), len(delivered)) == (5, 20)
    assert row["value"] == pytest.approx(0.25)


def test_avg_delivery_days_counts_the_time_of_day(synthetic_db):
    purchased = datetime.fromisoformat(synthetic_data.PURCHASED)
    durations = [
        (datetime.fromisoformat(order["delivered"]) - purchased).total_seconds() / 86400
        for order in ORDERS
        if delivered_by_today(order)
    ]

    row = single(synthetic_db, "avg_delivery_days")

    assert row["denominator"] == 20
    assert row["value"] == pytest.approx(sum(durations) / len(durations))


def test_delivery_metrics_leave_out_an_order_delivered_after_today(synthetic_db):
    # With o_delivered_future counted there would be 21 delivered orders.
    one_week_later = date(2018, 9, 8)

    today = single(synthetic_db, "late_delivery_rate")
    later = single(synthetic_db, "late_delivery_rate", today=one_week_later)

    assert today["denominator"] == 20
    assert later["denominator"] == 21


def test_avg_review_score(synthetic_db):
    row = single(synthetic_db, "avg_review_score")

    assert (row["numerator"], row["denominator"]) == (7, 2)
    assert row["value"] == pytest.approx(3.5)


def test_avg_review_score_counts_an_order_once(synthetic_db):
    # A second review for o_day14: its two scores (5 and 1) average to 3.
    synthetic_db.execute(
        "INSERT INTO order_reviews (review_id, order_id, review_score, "
        "review_creation_date) VALUES ('r_again', 'o_day14', 1, '2018-08-20 00:00:00')"
    )

    row = single(synthetic_db, "avg_review_score")

    assert row["denominator"] == 2
    assert row["value"] == pytest.approx((3 + 2) / 2)


def test_avg_review_score_leaves_out_a_review_written_after_today(synthetic_db):
    synthetic_db.execute(
        "INSERT INTO order_reviews (review_id, order_id, review_score, "
        "review_creation_date) VALUES ('r_later', 'o_day0', 1, '2018-09-03 00:00:00')"
    )

    assert single(synthetic_db, "avg_review_score")["denominator"] == 2


def test_seller_late_shipping_rate_counts_items(synthetic_db):
    handed_over = sum(
        len(items_of(order))
        for order in ORDERS
        if order.get("carrier", synthetic_data.HANDED_TO_CARRIER) is not None
    )

    row = single(synthetic_db, "seller_late_shipping_rate")

    # Late: the one item of o_seller_late and the second of o_seller_late_one_item.
    assert (row["numerator"], row["denominator"]) == (2, handed_over)
    assert handed_over == 25
    assert row["value"] == pytest.approx(0.08)


# --- Grouping -----------------------------------------------------------


def test_grouping_by_customer_state(varied_db):
    groups = grouped(varied_db, "order_count", ["customer_state"])

    assert {state: row["value"] for state, row in groups.items()} == {"RJ": 1, "SP": 28}


def test_grouping_by_purchase_month(varied_db):
    groups = grouped(varied_db, "cancel_rate", ["purchase_month"])

    assert groups["2018-06"]["denominator"] == 27
    assert groups["2018-06"]["numerator"] == 0
    assert groups["2018-07"]["denominator"] == 2
    assert groups["2018-07"]["value"] == pytest.approx(0.5)


def test_order_with_two_categories_is_counted_once_in_each(varied_db):
    groups = grouped(varied_db, "order_count", ["product_category_en"])

    assert groups["lighting"]["value"] == 1
    assert groups["furniture_decor"]["value"] == 29


def test_order_with_two_items_of_one_category_is_counted_once(synthetic_db):
    # o_two_items and o_seller_late_one_item each have two items of one category.
    groups = grouped(synthetic_db, "order_count", ["product_category_en"])

    assert groups == {
        "furniture_decor": {
            "product_category_en": "furniture_decor",
            "numerator": 29,
            "value": 29,
        }
    }


def test_late_delivery_rate_by_category_uses_distinct_pairs(varied_db):
    groups = grouped(varied_db, "late_delivery_rate", ["product_category_en"])

    assert groups["furniture_decor"]["denominator"] == 20
    assert groups["lighting"]["denominator"] == 1


def test_gmv_by_category_splits_an_order_by_its_items(varied_db):
    groups = grouped(varied_db, "gmv", ["product_category_en"])

    assert groups["lighting"]["value"] == pytest.approx(50.00)
    assert groups["furniture_decor"]["value"] == pytest.approx(3670.01 - 50.00)


def test_grouping_by_seller_state(varied_db):
    groups = grouped(varied_db, "seller_late_shipping_rate", ["seller_state"])

    assert groups["RJ"]["denominator"] == 1
    assert groups["SP"]["denominator"] == 24


def test_grouping_by_two_dimensions(varied_db):
    groups = grouped(varied_db, "order_count", ["customer_state", "purchase_month"])

    assert {key: row["value"] for key, row in groups.items()} == {
        ("RJ", "2018-06"): 1,
        ("SP", "2018-06"): 26,
        ("SP", "2018-07"): 2,
    }


def test_groups_come_back_sorted(varied_db):
    answer = run_metric(varied_db, "order_count", group_by=["purchase_month"])

    assert [row[0] for row in answer["rows"]] == ["2018-06", "2018-07"]


# --- Filters ------------------------------------------------------------


def test_filter_by_one_value(varied_db):
    row = single(varied_db, "order_count", filters={"customer_state": "RJ"})

    assert row["value"] == 1


def test_filter_by_a_list_of_values(varied_db):
    row = single(varied_db, "order_count", filters={"customer_state": ["RJ", "SP"]})

    assert row["value"] == 29


def test_filter_by_an_item_dimension_counts_each_order_once(varied_db):
    row = single(
        varied_db, "order_count", filters={"product_category_en": "furniture_decor"}
    )

    assert row["value"] == 29


def test_filter_by_purchase_period(varied_db):
    july = {"purchase_from": "2018-07-01", "purchase_to": "2018-07-31"}

    assert single(varied_db, "order_count", filters=july)["value"] == 2
    assert single(varied_db, "gmv", filters=july)["value"] == pytest.approx(100.00)


def test_filter_and_grouping_together(varied_db):
    groups = grouped(
        varied_db,
        "order_count",
        ["purchase_month"],
        filters={"customer_state": "SP"},
    )

    assert {month: row["value"] for month, row in groups.items()} == {
        "2018-06": 26,
        "2018-07": 2,
    }


def test_filter_value_is_bound_not_written_into_the_sql(synthetic_db):
    attack = "SP' OR '1'='1"

    answer = run_metric(synthetic_db, "order_count", filters={"customer_state": attack})

    assert attack not in answer["sql"]
    assert answer["params"]["customer_state_0"] == attack
    assert answer["rows"] == [[0, 0]]


# --- Ranking groups -----------------------------------------------------


def test_groups_can_be_ordered_by_value_and_cut(varied_db):
    answer = run_metric(
        varied_db,
        "order_count",
        group_by=["product_category_en"],
        order="value_desc",
        top=1,
    )

    assert answer["rows"] == [["furniture_decor", 29, 29]]
    assert answer["sql"].endswith("ORDER BY value DESC, product_category_en LIMIT 1")


def test_ascending_order(varied_db):
    answer = run_metric(
        varied_db, "order_count", group_by=["product_category_en"], order="value_asc"
    )

    assert [row[0] for row in answer["rows"]] == ["lighting", "furniture_decor"]


def test_min_count_keeps_groups_of_that_size_by_the_denominator(varied_db):
    # late_delivery_rate by category: furniture_decor has 20 delivered orders,
    # lighting has 1.
    answer = run_metric(
        varied_db, "late_delivery_rate", group_by=["product_category_en"], min_count=2
    )

    assert [row[0] for row in answer["rows"]] == ["furniture_decor"]
    assert "WHERE denominator >= :min_count" in answer["sql"]
    assert answer["params"]["min_count"] == 2


def test_min_count_uses_the_numerator_for_a_plain_total(varied_db):
    answer = run_metric(
        varied_db, "order_count", group_by=["customer_state"], min_count=2
    )

    assert [row[0] for row in answer["rows"]] == ["SP"]
    assert "WHERE numerator >= :min_count" in answer["sql"]


def test_equal_values_come_back_in_a_fixed_order(varied_db):
    answer = run_metric(
        varied_db, "cancel_rate", group_by=["customer_state"], order="value_desc"
    )

    # RJ has no cancelled order (0.0); SP has one.
    assert [row[0] for row in answer["rows"]] == ["SP", "RJ"]


def test_result_without_ranking_is_unchanged(synthetic_db):
    plain = run_metric(synthetic_db, "order_count", group_by=["customer_state"])

    assert plain["sql"].endswith("ORDER BY customer_state LIMIT 1000")
    assert "min_count" not in plain["params"]


@pytest.mark.parametrize(
    "ranking",
    [
        {"order": "biggest"},
        {"order": "value_desc; DROP TABLE orders"},
        {"top": 0},
        {"top": 5000},
        {"top": "5"},
        {"min_count": 0},
        {"min_count": "100"},
    ],
)
def test_invalid_ranking_is_refused(synthetic_db, ranking):
    answer = run_metric(synthetic_db, "order_count", **ranking)

    assert answer["error"] == "INVALID_RANKING"
    assert "sql" not in answer


# --- What comes back ----------------------------------------------------


def test_answer_holds_the_sql_the_caveat_and_the_bound_today(synthetic_db):
    answer = run_metric(synthetic_db, "late_delivery_rate")

    assert answer["metric"] == "late_delivery_rate"
    assert answer["columns"] == ["numerator", "denominator", "value"]
    assert (
        answer["caveat"] == load_semantic_layer().metrics["late_delivery_rate"].caveat
    )
    assert ":simulated_today" in answer["sql"]
    assert answer["params"] == {"simulated_today": "2018-09-01"}


@pytest.mark.parametrize("metric_name", sorted(REQUIRED_METRICS))
def test_every_metric_binds_the_simulated_today(synthetic_db, metric_name):
    answer = run_metric(synthetic_db, metric_name)

    assert ":simulated_today" in answer["sql"]
    assert answer["params"]["simulated_today"] == "2018-09-01"


@pytest.mark.parametrize("metric_name", sorted(REQUIRED_METRICS))
def test_every_metric_runs_with_each_of_its_dimensions(synthetic_db, metric_name):
    for dimension in load_semantic_layer().metrics[metric_name].dimensions:
        answer = run_metric(synthetic_db, metric_name, group_by=[dimension])

        assert answer["columns"][0] == dimension
        assert answer["rows"]


def test_the_generated_sql_is_one_select(synthetic_db):
    sql = run_metric(synthetic_db, "gmv", group_by=["seller_state"])["sql"]

    assert sql.startswith("SELECT ")
    assert ";" not in sql
    assert sql.endswith("LIMIT 1000")


def test_metric_runs_on_a_read_only_connection(synthetic_db_path):
    conn = sqlite3.connect(f"file:{synthetic_db_path}?mode=ro", uri=True)
    try:
        assert single(conn, "order_count")["value"] == 29
    finally:
        conn.close()


def test_running_a_metric_writes_nothing(synthetic_db):
    for metric_name in REQUIRED_METRICS:
        run_metric(synthetic_db, metric_name)

    assert synthetic_db.total_changes == 0


# --- Refusals -----------------------------------------------------------


def test_unknown_metric_is_refused_with_the_defined_ones(synthetic_db):
    answer = run_metric(synthetic_db, "revenue")

    assert answer["error"] == "UNKNOWN_METRIC"
    for name in REQUIRED_METRICS:
        assert name in answer["message"]


@pytest.mark.parametrize(
    ("metric_name", "dimension"),
    [
        ("order_count", "customer_city"),
        ("order_count", "o.order_id"),
        ("cancel_rate", "seller_state"),
        ("avg_order_value", "product_category_en"),
    ],
)
def test_dimension_the_metric_does_not_allow_is_refused(
    synthetic_db, metric_name, dimension
):
    answer = run_metric(synthetic_db, metric_name, group_by=[dimension])

    assert answer["error"] == "INVALID_DIMENSION"
    assert dimension in answer["message"]
    assert "sql" not in answer


def test_more_than_two_dimensions_are_refused(synthetic_db):
    answer = run_metric(
        synthetic_db,
        "gmv",
        group_by=["customer_state", "purchase_month", "seller_state"],
    )

    assert answer["error"] == "INVALID_DIMENSION"


def test_the_same_dimension_twice_is_refused(synthetic_db):
    answer = run_metric(
        synthetic_db, "gmv", group_by=["customer_state", "customer_state"]
    )

    assert answer["error"] == "INVALID_DIMENSION"


def test_two_item_dimensions_are_refused_for_an_order_metric(synthetic_db):
    both = ["product_category_en", "seller_state"]

    assert run_metric(synthetic_db, "order_count", group_by=both)["error"] == (
        "INVALID_DIMENSION"
    )
    # Fine for a metric counted per item: nothing is counted twice.
    assert run_metric(synthetic_db, "gmv", group_by=both)["rows"]


@pytest.mark.parametrize(
    "filters",
    [
        {"customer_city": "sao paulo"},
        {"o.order_id": "x"},
        {"customer_state = 'SP' OR 1": "1"},
    ],
)
def test_filter_on_something_else_than_an_allowed_dimension_is_refused(
    synthetic_db, filters
):
    answer = run_metric(synthetic_db, "order_count", filters=filters)

    assert answer["error"] == "INVALID_FILTER"
    assert "sql" not in answer


@pytest.mark.parametrize("value", [5, None, [], ["SP", 5], {"a": "b"}])
def test_filter_value_that_is_not_text_is_refused(synthetic_db, value):
    answer = run_metric(synthetic_db, "order_count", filters={"customer_state": value})

    assert answer["error"] == "INVALID_FILTER"


@pytest.mark.parametrize("value", ["yesterday", "2018-13-01", "01/07/2018", 20180701])
def test_period_filter_that_is_not_a_date_is_refused(synthetic_db, value):
    answer = run_metric(synthetic_db, "order_count", filters={"purchase_from": value})

    assert answer["error"] == "INVALID_FILTER"
