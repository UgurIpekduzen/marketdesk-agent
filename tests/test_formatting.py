"""Tests for how numbers and money are written for the reader."""

import pytest

from src import messages
from src.formatting import (
    MAX_TEXT_ROWS,
    format_amount,
    format_money,
    format_number,
    readable_sql,
    readable_table,
    table_text,
    with_separators,
    worth_a_table,
)


def test_separators_are_swapped_the_turkish_way():
    assert with_separators("1,234,567.89") == "1.234.567,89"


@pytest.mark.parametrize(
    ("value", "whole", "text"),
    [
        (7269, True, "7.269"),
        (494, True, "494"),
        (1255695.13, False, "1.255.695,13"),
        (4.04, False, "4,04"),
        (0.007619, False, "0,0076"),
        (-1234.5, False, "-1.234,50"),
        # A whole column the table library turned into decimals.
        (7269.0, True, "7.269"),
    ],
)
def test_numbers_are_written_the_turkish_way(value, whole, text):
    assert format_number(value, whole) == text


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        ("133.14", "133,14"),
        ("1250.00", "1.250,00"),
        ("1250", "1.250,00"),
        ("0.5", "0,50"),
        ("1234567.89", "1.234.567,89"),
    ],
)
def test_money_is_written_the_turkish_way_with_two_decimals(amount, text):
    assert format_amount(amount) == text


def test_money_carries_its_currency():
    assert format_money("115.00") == "115,00 BRL"


def test_a_table_as_text_has_turkish_headers_and_numbers_aligned():
    table = readable_table(
        {
            "columns": ["purchase_month", "numerator", "value"],
            "rows": [
                ["2018-01", 7269, 7269],
                ["2018-02", 728, 728],
                ["2018-03", None, None],
            ],
        }
    )

    assert table_text(table) == (
        "Ay      | Değer\n--------+------\n2018-01 | 7.269\n2018-02 |   728\n2018-03 |"
    )


def test_a_long_table_as_text_says_how_many_rows_it_left_out():
    rows = [[f"S{number}", number] for number in range(MAX_TEXT_ROWS + 7)]
    table = readable_table({"columns": ["state", "orders"], "rows": rows})

    lines = table_text(table).splitlines()

    assert len(lines) == 2 + MAX_TEXT_ROWS + 1
    assert lines[-1] == messages.TABLE_ROWS_LEFT_OUT.format(count=7)


def test_a_single_value_is_not_worth_a_table():
    def readable(columns, rows):
        return readable_table({"columns": columns, "rows": rows})

    # A plain total: the repeated numerator goes, one cell is left.
    assert not worth_a_table(readable(["numerator", "value"], [[29, 29]]))
    assert worth_a_table(
        readable(["numerator", "denominator", "value"], [[5, 20, 0.25]])
    )
    assert worth_a_table(readable(["state", "value"], [["SP", 1], ["RJ", 2]]))


QUERY = (
    "SELECT purchase_month, COUNT(*) AS numerator FROM orders AS o "
    "WHERE DATE(o.order_purchase_timestamp) <= DATE(:simulated_today) "
    "GROUP BY purchase_month ORDER BY purchase_month LIMIT 5"
)


def test_a_query_is_laid_out_one_clause_per_line():
    lines = readable_sql(QUERY).splitlines()

    assert lines[0] == "SELECT"
    for clause in ("FROM orders AS o", "WHERE", "GROUP BY", "ORDER BY", "LIMIT 5"):
        assert clause in lines
    # The placeholder the query is run with is kept.
    assert ":simulated_today" in readable_sql(QUERY)


def test_a_query_laid_out_reads_the_same_to_the_parser():
    import sqlglot

    def tree(sql):
        return sqlglot.parse_one(sql, read="sqlite")

    assert tree(readable_sql(QUERY)) == tree(QUERY)


def test_a_query_the_parser_cannot_read_is_shown_as_it_is():
    broken = "SELEC purchase_month FRM orders WHERE ("

    assert readable_sql(broken) == broken
