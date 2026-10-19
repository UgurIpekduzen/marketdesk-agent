"""How numbers, money and result tables are written for the reader.

Plain functions with no page framework, so the page, the command line and
the evaluation write them alike. They write the Turkish way: a dot between thousands and
a comma before the decimals. Only how a value is written changes; the value
itself is never touched.
"""

from decimal import Decimal

import sqlglot
from sqlglot import errors

import config
from src import messages
from src.knowledge.semantic_layer import (
    DENOMINATOR,
    NUMERATOR,
    VALUE,
    load_semantic_layer,
)

# Headers of a result table: the dimensions by name, and the columns every
# metric result has.
COLUMN_HEADERS = {
    **messages.UI_TABLE_DIMENSIONS,
    NUMERATOR: messages.UI_COLUMN_NUMERATOR,
    DENOMINATOR: messages.UI_COLUMN_DENOMINATOR,
    VALUE: messages.UI_COLUMN_VALUE,
}
# A result written as text shows at most this many rows.
MAX_TEXT_ROWS = 50


def with_separators(text: str) -> str:
    """Python's separators turned into the reader's: 1,234.5 -> 1.234,5."""
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_number(value: float, whole: bool) -> str:
    """A number: 7.269; 1.255.695,13; 0,0076.

    A whole number keeps no decimals. Otherwise two decimals, or four below
    1, where rates live and two would round them away.
    """
    if whole:
        return with_separators(f"{round(value):,}")
    return with_separators(f"{value:,.{2 if abs(value) >= 1 else 4}f}")


def format_amount(amount: str) -> str:
    """A money amount, always with two decimals: 1.250,00.

    Read as a Decimal, not a float, so no cent is lost on the way.
    """
    return with_separators(f"{Decimal(amount):,.2f}")


def format_money(amount: str) -> str:
    """A money amount with its currency: 1.250,00 BRL."""
    return messages.MONEY.format(amount=format_amount(amount))


def readable_table(table: dict) -> dict:
    """A result table as the reader sees it.

    The columns the semantic layer names get Turkish headers; a plain total
    has a numerator that only repeats the value, and that column is left
    out. For each numeric column it says whether it holds whole numbers,
    decided here on the raw values: the page's table library turns a whole
    column with a gap into decimals.
    """
    columns = list(table["columns"])
    rows = [list(row) for row in table["rows"]]
    if NUMERATOR in columns and VALUE in columns:
        numerator, value = columns.index(NUMERATOR), columns.index(VALUE)
        if all(row[numerator] == row[value] for row in rows):
            del columns[numerator]
            for row in rows:
                del row[numerator]
    headers = [COLUMN_HEADERS.get(column, column) for column in columns]
    numbers = {}
    for position, header in enumerate(headers):
        values = [row[position] for row in rows if row[position] is not None]
        if values and all(
            isinstance(item, int | float) and not isinstance(item, bool)
            for item in values
        ):
            numbers[header] = all(isinstance(item, int) for item in values)
    return {"columns": headers, "rows": rows, "numbers": numbers}


def worth_a_table(table: dict) -> bool:
    """Whether a readable table says more than the answer's sentence.

    A single value is said in the sentence; a table of one cell would only
    repeat it.
    """
    return len(table["rows"]) > 1 or len(table["columns"]) > 1


def table_text(table: dict) -> str:
    """A readable table as plain text, for the command line and the judge.

    Numbers are written like everywhere else and aligned right; a long
    table is cut, and says how many rows it left out.
    """
    shown = table["rows"][:MAX_TEXT_ROWS]
    cells = [
        [
            ""
            if value is None
            else format_number(value, table["numbers"][header])
            if header in table["numbers"]
            else str(value)
            for header, value in zip(table["columns"], row, strict=True)
        ]
        for row in shown
    ]
    widths = [
        max(len(text) for text in [header, *(row[position] for row in cells)])
        for position, header in enumerate(table["columns"])
    ]

    def line(texts: list[str]) -> str:
        return " | ".join(
            text.rjust(width) if header in table["numbers"] else text.ljust(width)
            for text, width, header in zip(texts, widths, table["columns"], strict=True)
        ).rstrip()

    lines = [line(table["columns"]), "-+-".join("-" * width for width in widths)]
    lines += [line(row) for row in cells]
    left_out = len(table["rows"]) - len(shown)
    if left_out:
        lines.append(messages.TABLE_ROWS_LEFT_OUT.format(count=left_out))
    return "\n".join(lines)


def readable_sql(query: str) -> str:
    """A query laid out on lines, one clause per line, for a narrow panel.

    Only for reading: the query that ran is the one given. The parser that
    checks queries lays it out; a query it cannot read (a failed attempt)
    is shown as it is.
    """
    try:
        return sqlglot.transpile(query, read="sqlite", write="sqlite", pretty=True)[0]
    except errors.SqlglotError:
        return query


def how_computed(computation: dict) -> str:
    """One metric call in words: metric, grouping, filters, period, ranking.

    computation holds what the ops agent passed to run_metric: metric,
    filters, group_by and ranking. Written from the call itself, so it says
    what was computed whatever the answer says.
    """
    metric = load_semantic_layer().metrics[computation["metric"]]
    labels = messages.UI_TABLE_DIMENSIONS
    filters = dict(computation.get("filters") or {})
    start, end = filters.pop("purchase_from", None), filters.pop("purchase_to", None)
    ranking = computation.get("ranking") or {}
    parts = [metric.description]
    if computation.get("group_by"):
        parts.append(
            messages.COMPUTED_GROUP_BY.format(
                dimensions=", ".join(
                    labels.get(name, name) for name in computation["group_by"]
                )
            )
        )
    if filters:
        parts.append(
            messages.COMPUTED_FILTER.format(
                filters="; ".join(
                    f"{labels.get(name, name)} = {', '.join(map(str, values))}"
                    for name, values in filters.items()
                )
            )
        )
    if start and end:
        parts.append(messages.COMPUTED_PERIOD_BOTH.format(start=start, end=end))
    elif start:
        parts.append(messages.COMPUTED_PERIOD_FROM.format(start=start))
    elif end:
        parts.append(messages.COMPUTED_PERIOD_TO.format(end=end))
    if ranking.get("min_count"):
        parts.append(
            messages.COMPUTED_MIN_COUNT.format(
                count=ranking["min_count"], unit=messages.COMPUTED_UNITS[metric.grain]
            )
        )
    if ranking.get("order") in messages.COMPUTED_ORDER:
        parts.append(messages.COMPUTED_ORDER[ranking["order"]])
    if ranking.get("top"):
        parts.append(messages.COMPUTED_TOP.format(top=ranking["top"]))
    parts.append(
        messages.COMPUTED_SCOPE.format(today=config.SIMULATED_TODAY.isoformat())
    )
    return " · ".join(parts)
