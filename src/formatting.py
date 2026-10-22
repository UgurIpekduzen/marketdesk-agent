"""How numbers, money and result tables are written for the reader.

Plain functions with no page framework, so the page, the command line and
the evaluation write them alike. They write the session's language's way:
Turkish puts a dot between thousands and a comma before the decimals
(1.234,5), English the other way round (1,234.5). Turkish is the default.
Only how a value is written changes; the value itself is never touched.
"""

from decimal import Decimal

import sqlglot
from sqlglot import errors

import config
from src.i18n import DEFAULT_LANGUAGE, Language, catalog
from src.knowledge.semantic_layer import (
    DENOMINATOR,
    NUMERATOR,
    VALUE,
    load_semantic_layer,
)

# A result written as text shows at most this many rows.
MAX_TEXT_ROWS = 50


def column_headers(language: Language = DEFAULT_LANGUAGE) -> dict[str, str]:
    """Headers of a result table: the dimensions by name, and the columns
    every metric result has."""
    texts = catalog(language)
    return {
        **texts.UI_TABLE_DIMENSIONS,
        NUMERATOR: texts.UI_COLUMN_NUMERATOR,
        DENOMINATOR: texts.UI_COLUMN_DENOMINATOR,
        VALUE: texts.UI_COLUMN_VALUE,
    }


def with_separators(text: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """Python's separators turned into the reader's: 1,234.5 stays as it is
    in English and becomes 1.234,5 in Turkish."""
    if language == Language.EN:
        return text
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_number(
    value: float, whole: bool, language: Language = DEFAULT_LANGUAGE
) -> str:
    """A number: 7.269; 1.255.695,13; 0,0076 (in English 7,269; 1,255,695.13;
    0.0076).

    A whole number keeps no decimals. Otherwise two decimals, or four below
    1, where rates live and two would round them away.
    """
    if whole:
        return with_separators(f"{round(value):,}", language)
    return with_separators(f"{value:,.{2 if abs(value) >= 1 else 4}f}", language)


def format_amount(amount: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """A money amount, always with two decimals: 1.250,00 (1,250.00).

    Read as a Decimal, not a float, so no cent is lost on the way.
    """
    return with_separators(f"{Decimal(amount):,.2f}", language)


def format_money(amount: str, language: Language = DEFAULT_LANGUAGE) -> str:
    """A money amount with its currency: 1.250,00 BRL (1,250.00 BRL)."""
    return catalog(language).MONEY.format(amount=format_amount(amount, language))


def readable_table(table: dict, language: Language = DEFAULT_LANGUAGE) -> dict:
    """A result table as the reader sees it.

    The columns the semantic layer names get headers in the language; a plain total
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
    known = column_headers(language)
    headers = [known.get(column, column) for column in columns]
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


def table_text(table: dict, language: Language = DEFAULT_LANGUAGE) -> str:
    """A readable table as plain text, for the command line and the judge.

    Numbers are written like everywhere else and aligned right; a long
    table is cut, and says how many rows it left out.
    """
    shown = table["rows"][:MAX_TEXT_ROWS]
    cells = [
        [
            ""
            if value is None
            else format_number(value, table["numbers"][header], language)
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
        lines.append(catalog(language).TABLE_ROWS_LEFT_OUT.format(count=left_out))
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


def how_computed(computation: dict, language: Language = DEFAULT_LANGUAGE) -> str:
    """One metric call in words: metric, grouping, filters, period, ranking.

    computation holds what the ops agent passed to run_metric: metric,
    filters, group_by and ranking. Written from the call itself, so it says
    what was computed whatever the answer says.
    """
    metric = load_semantic_layer().metrics[computation["metric"]]
    messages = catalog(language)
    labels = messages.UI_TABLE_DIMENSIONS
    filters = dict(computation.get("filters") or {})
    start, end = filters.pop("purchase_from", None), filters.pop("purchase_to", None)
    ranking = computation.get("ranking") or {}
    parts = [metric.description_in(language)]
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
    if computation.get("for_report_sellers"):
        parts.append(messages.COMPUTED_REPORT_SELLERS)
    return " · ".join(parts)


# The report's fields in table order, as the readable table's columns.
SELLER_REPORT_FIELDS = (
    "seller", "items", "late_rate", "orders", "gmv", "avg_review_score",
)  # fmt: skip


def seller_report_table(report: dict, language: Language = DEFAULT_LANGUAGE) -> dict:
    """The seller report's rows as a readable table (same shape as
    readable_table's): headers in the language, the late rate as a percentage."""
    headers = catalog(language).SELLER_REPORT_COLUMNS
    rows = [
        [
            None
            if row[field] is None
            else row[field] * 100
            if field == "late_rate"
            else row[field]
            for field in SELLER_REPORT_FIELDS
        ]
        for row in report["rows"]
    ]
    return {
        "columns": [headers[field] for field in SELLER_REPORT_FIELDS],
        "rows": rows,
        "numbers": {
            headers[field]: field in ("items", "orders")
            for field in SELLER_REPORT_FIELDS[1:]
        },
    }


def report_computation(source: dict) -> dict:
    """One metric call of the report as how_computed reads it: the sellers
    of the table are not listed, the line says they are the filter."""
    return {
        "metric": source["metric"],
        "filters": {k: v for k, v in source["filters"].items() if k != "seller_key"},
        "group_by": source["group_by"],
        "ranking": source["ranking"],
        "for_report_sellers": "seller_key" in source["filters"],
    }


def seller_report_sources(
    report: dict, language: Language = DEFAULT_LANGUAGE
) -> list[tuple[str, str]]:
    """For each metric behind the report: how it was computed, in words, and
    the SQL that ran."""
    lines = []
    for source in report["sources"]:
        words = how_computed(report_computation(source), language)
        lines.append((words, source["sql"]))
    return lines
