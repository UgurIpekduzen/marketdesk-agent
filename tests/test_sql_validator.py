"""Tests for the SQL validator. No database is needed: it only reads text."""

import pytest

from src.knowledge.sql_validator import SqlRejected, validate

# What exists in the database besides the views.
RAW_TABLES = (
    "orders",
    "customers",
    "order_items",
    "order_payments",
    "order_reviews",
    "products",
    "sellers",
    "geolocation",
    "product_category_name_translation",
    "return_requests",
)


def check(query, **kwargs):
    return validate(query, RAW_TABLES, **kwargs)


def rejection(query):
    with pytest.raises(SqlRejected) as caught:
        check(query)
    return caught.value.code


# --- Queries that pass --------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "SELECT COUNT(*) FROM v_orders",
        "select order_status, count(*) from v_orders group by order_status",
        (
            "SELECT o.customer_state, SUM(i.price) FROM v_orders AS o "
            "JOIN v_order_items AS i ON i.order_key = o.order_key GROUP BY 1"
        ),
        (
            "WITH late AS (SELECT order_key FROM v_orders WHERE order_status = 'shipped') "
            "SELECT COUNT(*) FROM late"
        ),
        "SELECT order_key FROM v_orders UNION SELECT order_key FROM v_order_items",
        "SELECT * FROM (SELECT order_key FROM v_orders) AS inner_rows",
        (
            "SELECT COUNT(*) FROM v_orders WHERE order_key IN "
            "(SELECT order_key FROM v_order_reviews WHERE review_score < 3)"
        ),
        "SELECT COUNT(*) FROM V_ORDERS",
        "SELECT 1",
    ],
)
def test_select_over_the_views_passes(query):
    assert check(query).startswith(("SELECT", "WITH"))


def test_trailing_semicolon_and_comment_are_fine():
    assert check("SELECT COUNT(*) FROM v_orders; -- how many") == (
        "SELECT COUNT(*) FROM v_orders LIMIT 1000"
    )


def test_date_functions_pass_and_come_out_unchanged():
    sql = check(
        "SELECT strftime('%Y-%m', order_purchase_timestamp), "
        "AVG(julianday(order_delivered_customer_date) - "
        "julianday(order_purchase_timestamp)), DATE(order_approved_at) "
        "FROM v_orders GROUP BY 1"
    )

    assert "STRFTIME('%Y-%m', order_purchase_timestamp)" in sql
    assert "JULIANDAY(order_delivered_customer_date)" in sql
    assert "DATE(order_approved_at)" in sql


# --- The row limit ------------------------------------------------------


def test_limit_is_added_when_missing():
    assert check("SELECT order_key FROM v_orders ORDER BY order_key") == (
        "SELECT order_key FROM v_orders ORDER BY order_key LIMIT 1000"
    )


def test_smaller_limit_is_kept():
    assert check("SELECT order_key FROM v_orders LIMIT 5").endswith("LIMIT 5")


def test_limit_with_offset_is_kept():
    assert check("SELECT order_key FROM v_orders LIMIT 10 OFFSET 20").endswith(
        "LIMIT 10 OFFSET 20"
    )


@pytest.mark.parametrize(
    "limit",
    ["LIMIT 5000", "LIMIT 1001", "LIMIT -1", "LIMIT 500 + 600", "LIMIT 5, 2000"],
)
def test_limit_above_the_maximum_or_not_a_plain_number_is_lowered(limit):
    sql = check(f"SELECT order_key FROM v_orders {limit}")

    assert "LIMIT 1000" in sql
    assert "5000" not in sql
    assert "2000" not in sql
    assert "-1" not in sql


def test_limit_is_added_to_a_union():
    sql = check(
        "SELECT order_key FROM v_orders UNION SELECT order_key FROM v_order_items"
    )

    assert sql.endswith("LIMIT 1000")


def test_limit_inside_a_subquery_does_not_count_as_the_limit():
    sql = check("SELECT * FROM (SELECT order_key FROM v_orders LIMIT 5000) AS x")

    assert sql.endswith("LIMIT 1000")


def test_the_maximum_can_be_set():
    assert check("SELECT order_key FROM v_orders", max_rows=10).endswith("LIMIT 10")


# --- One statement, and only a SELECT -----------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM v_orders; DROP TABLE orders",
        "SELECT 1; SELECT 2",
        "SELECT * FROM v_orders WHERE order_status = ''; DROP TABLE orders; --'",
        "SELECT 1; ATTACH DATABASE 'x.db' AS x",
    ],
)
def test_statement_chain_is_refused(query):
    assert rejection(query) == "MULTIPLE_STATEMENTS"


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE orders",
        "DELETE FROM orders",
        "UPDATE orders SET order_status = 'canceled'",
        "INSERT INTO return_requests (order_id) VALUES ('x')",
        "ALTER TABLE orders ADD COLUMN note TEXT",
        "CREATE TABLE copy AS SELECT * FROM v_orders",
        "CREATE VIEW v_all AS SELECT * FROM customers",
        "ATTACH DATABASE 'other.db' AS other",
        "DETACH DATABASE other",
        "PRAGMA table_info(customers)",
        "PRAGMA query_only = OFF",
        "VACUUM INTO 'copy.db'",
        "EXPLAIN SELECT * FROM v_orders",
        "BEGIN",
        "VALUES (1)",
        "(SELECT 1)",
    ],
)
def test_anything_but_a_select_is_refused(query):
    assert rejection(query) in ("NOT_A_SELECT", "FORBIDDEN_STATEMENT")


@pytest.mark.parametrize("query", ["", "   ", ";", "-- only a comment"])
def test_empty_query_is_refused(query):
    assert rejection(query) == "EMPTY_QUERY"


@pytest.mark.parametrize("query", ["SELEC 1", "SELECT FROM WHERE", "SELECT (1"])
def test_query_that_does_not_parse_is_refused(query):
    assert rejection(query) == "PARSE_ERROR"


def test_write_hidden_in_a_cte_is_refused():
    query = "WITH gone AS (DELETE FROM orders RETURNING *) SELECT * FROM gone"

    assert rejection(query) == "FORBIDDEN_STATEMENT"


def test_select_into_is_refused():
    assert rejection("SELECT order_key INTO copy FROM v_orders") in (
        "FORBIDDEN_STATEMENT",
        "TABLE_NOT_ALLOWED",
    )


# --- Tables -------------------------------------------------------------


@pytest.mark.parametrize("table", RAW_TABLES)
def test_raw_table_is_refused(table):
    assert rejection(f"SELECT * FROM {table}") == "TABLE_NOT_ALLOWED"


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM CUSTOMERS",
        'SELECT * FROM "customers"',
        "SELECT * FROM main.customers",
        "SELECT * FROM main.v_orders",
        "SELECT * FROM temp.anything",
        "SELECT * FROM v_orders, customers",
        "SELECT * FROM v_orders AS o JOIN customers AS c ON 1 = 1",
        "SELECT (SELECT customer_city FROM customers LIMIT 1) FROM v_orders",
        "SELECT * FROM v_orders WHERE order_key IN (SELECT rowid FROM customers)",
        "SELECT * FROM v_orders UNION SELECT * FROM customers",
        "WITH c AS (SELECT * FROM customers) SELECT * FROM c",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM sqlite_schema",
        "SELECT * FROM sqlite_temp_master",
        "SELECT * FROM v_does_not_exist",
    ],
)
def test_raw_table_is_refused_wherever_it_is_named(query):
    assert rejection(query) == "TABLE_NOT_ALLOWED"


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM pragma_table_info('customers')",
        "SELECT * FROM v_orders AS o JOIN json_each('[1]') AS j",
        "SELECT * FROM pragma_database_list",
    ],
)
def test_function_used_as_a_table_is_refused(query):
    assert rejection(query) == "TABLE_NOT_ALLOWED"


@pytest.mark.parametrize(
    "query",
    [
        # Outside the subquery, "customers" is the real table again.
        (
            "SELECT * FROM customers WHERE 1 IN "
            "(WITH customers AS (SELECT 1 AS x) SELECT x FROM customers)"
        ),
        "WITH customers AS (SELECT 1 AS x) SELECT * FROM customers",
        "WITH v_orders AS (SELECT 1 AS x) SELECT * FROM v_orders",
        "WITH sqlite_master AS (SELECT 1 AS x) SELECT * FROM sqlite_master",
        "WITH Orders AS (SELECT 1 AS x) SELECT * FROM Orders",
    ],
)
def test_cte_may_not_take_the_name_of_something_real(query):
    assert rejection(query) == "TABLE_NOT_ALLOWED"


def test_recursive_cte_over_nothing_passes():
    sql = check(
        "WITH RECURSIVE counter(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM counter "
        "WHERE x < 5) SELECT x FROM counter"
    )

    assert sql.endswith("LIMIT 1000")


# --- Functions ----------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        "load_extension('evil')",
        "readfile('/etc/passwd')",
        "writefile('x', 'y')",
        "fts3_tokenizer('x')",
        "edit('x')",
        "something_unknown(1)",
    ],
)
def test_function_outside_the_list_is_refused(call):
    assert rejection(f"SELECT {call} FROM v_orders") == "FUNCTION_NOT_ALLOWED"


def test_rejection_names_what_was_wrong():
    with pytest.raises(SqlRejected) as caught:
        check("SELECT * FROM v_orders JOIN customers ON 1 = 1")

    assert caught.value.code == "TABLE_NOT_ALLOWED"
    assert caught.value.detail == "customers"


# --- Items and payments together -------------------------------------------

ITEMS_WITH_PAYMENTS = (
    "SELECT AVG(f) FROM (SELECT i.order_key, SUM(i.freight_value) AS f "
    "FROM v_order_items AS i JOIN v_order_payments AS p ON p.order_key = i.order_key "
    "WHERE p.payment_type = 'credit_card' GROUP BY i.order_key)"
)


@pytest.mark.parametrize(
    "query",
    [
        ITEMS_WITH_PAYMENTS,
        (
            "SELECT 1 FROM v_order_items AS i, v_order_payments AS p "
            "WHERE i.order_key = p.order_key"
        ),
        "SELECT 1 FROM v_order_items CROSS JOIN v_order_payments",
        "SELECT 1 FROM v_order_payments LEFT JOIN v_order_items USING (order_key)",
        (
            "WITH both AS (SELECT * FROM v_order_items JOIN v_order_payments "
            "USING (order_key)) SELECT COUNT(*) FROM both"
        ),
        (
            "SELECT 1 FROM v_orders WHERE order_key IN (SELECT i.order_key "
            "FROM v_order_items AS i JOIN v_order_payments AS p USING (order_key))"
        ),
        "SELECT 1 FROM v_order_items JOIN V_ORDER_PAYMENTS USING (order_key)",
    ],
)
def test_items_and_payments_in_one_place_are_refused(query):
    assert rejection(query) == "JOIN_FANS_OUT"


def test_the_refusal_names_the_two_views():
    with pytest.raises(SqlRejected) as caught:
        check(ITEMS_WITH_PAYMENTS)

    assert caught.value.detail == "v_order_items and v_order_payments"


@pytest.mark.parametrize(
    "query",
    [
        # Filtering by payment in a subquery: the right form.
        (
            "SELECT AVG(f) FROM (SELECT SUM(freight_value) AS f FROM v_order_items "
            "WHERE order_key IN (SELECT order_key FROM v_order_payments "
            "WHERE payment_type = 'credit_card') GROUP BY order_key)"
        ),
        # Each summed per order in a subquery of its own, then joined.
        (
            "SELECT a.order_key FROM (SELECT order_key, SUM(price) AS p "
            "FROM v_order_items GROUP BY order_key) AS a JOIN (SELECT order_key, "
            "SUM(payment_value) AS v FROM v_order_payments GROUP BY order_key) AS b "
            "ON a.order_key = b.order_key"
        ),
        # Items with the other views.
        "SELECT 1 FROM v_order_items AS i JOIN v_orders AS o USING (order_key)",
        "SELECT 1 FROM v_order_items AS i JOIN v_order_reviews AS r USING (order_key)",
        "SELECT 1 FROM v_order_payments AS p JOIN v_orders AS o USING (order_key)",
        # Two parts of a UNION, one view each.
        (
            "SELECT order_key FROM v_order_items UNION "
            "SELECT order_key FROM v_order_payments"
        ),
    ],
)
def test_items_and_payments_kept_apart_pass(query):
    assert check(query)
