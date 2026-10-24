"""Runs a free SQL query, read-only.

Three layers stand between a query and the data, each enough to stop a
write on its own:

1. the validator: one SELECT, over the safe views only;
2. the connection: opened read-only, so SQLite itself refuses every write;
3. the attach limit set to zero, because a read-only connection could
   otherwise still ATTACH, and so create, another database file.

A query is also stopped when it runs too long, never returns more rows
than the limit, and cannot build a value or an answer beyond the limits of
the engine: the timeout counts steps, and one call of a function that makes
a huge string is one step.

The agents always run with the safe views. Only the raw-schema baseline of
the evaluation passes another list of tables, and it never sends the rows
to a model.
"""

import sqlite3
import time
from pathlib import Path

import config
from src import messages
from src.knowledge.safe_views import ALLOWED_VIEWS
from src.knowledge.sql_validator import SqlRejected, validate

# How many SQLite instructions run between two looks at the deadline.
PROGRESS_STEPS = 1000


def connect_read_only(db_path: Path | str) -> sqlite3.Connection:
    """Open the database so that nothing can be written or attached."""
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    # No value longer than this can be made, by a function or otherwise.
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, config.SQL_MAX_VALUE_BYTES)
    # The backstop for the memory of the engine. The setting is for the whole
    # process, not only this connection.
    conn.execute(f"PRAGMA hard_heap_limit = {config.SQL_HEAP_LIMIT_BYTES}")
    return conn


def result_bytes(rows: list[list]) -> int:
    """How many characters of text and bytes of blobs the rows hold."""
    return sum(
        len(value) for row in rows for value in row if isinstance(value, str | bytes)
    )


def existing_names(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Names of everything in the database: tables, views and indexes."""
    return tuple(row[0] for row in conn.execute("SELECT name FROM sqlite_master"))


def run_sql(
    db_path: Path | str,
    query: str,
    timeout_seconds: float = config.SQL_TIMEOUT_SECONDS,
    max_rows: int = config.SQL_MAX_ROWS,
    allowed_tables: tuple[str, ...] = ALLOWED_VIEWS,
) -> dict:
    """Run one read-only SELECT over the safe views and return its rows.

    Use it only when no metric from list_metrics answers the question. The
    query may read these views and nothing else: v_orders, v_order_items,
    v_order_payments, v_order_reviews, v_return_requests. Join them on
    order_key. There are no order or customer ids, cities or zip codes;
    use customer_key to count customers and customer_state or seller_state
    for places. Dates are text: use DATE() and julianday().

    The result holds the columns, the rows (at most 1000; a LIMIT is added
    when missing) and the SQL that was run. A refused query answers
    {"error": "SQL_REJECTED", "reason": ..., "message": ...}; a query that
    fails in the database answers SQL_ERROR with the database's message,
    and one that runs too long answers SQL_TIMEOUT.
    """
    conn = connect_read_only(db_path)
    try:
        try:
            sql = validate(
                query, existing_names(conn), allowed_tables, max_rows=max_rows
            )
        except SqlRejected as rejected:
            return {
                "error": "SQL_REJECTED",
                "reason": rejected.code,
                "detail": rejected.detail,
                "message": messages.SQL_REJECTED[rejected.code].format(
                    allowed=", ".join(allowed_tables)
                ),
            }

        deadline = time.monotonic() + timeout_seconds
        timed_out = False

        def past_deadline() -> bool:
            # A true value makes SQLite stop the running query.
            nonlocal timed_out
            timed_out = time.monotonic() > deadline
            return timed_out

        conn.set_progress_handler(past_deadline, PROGRESS_STEPS)
        try:
            cursor = conn.execute(sql)
            columns = [column[0] for column in cursor.description]
            rows = [list(row) for row in cursor.fetchmany(max_rows)]
            if result_bytes(rows) > config.SQL_MAX_RESULT_BYTES:
                return {
                    "error": "SQL_ERROR",
                    "detail": "RESULT_TOO_LARGE",
                    "message": messages.SQL_RESULT_TOO_LARGE,
                    "sql": sql,
                }
        except sqlite3.Error as failure:
            if timed_out:
                return {
                    "error": "SQL_TIMEOUT",
                    "message": messages.SQL_TIMEOUT.format(seconds=timeout_seconds),
                    "sql": sql,
                }
            return {
                "error": "SQL_ERROR",
                "detail": str(failure),
                "message": messages.SQL_ERROR,
                "sql": sql,
            }
        return {"columns": columns, "rows": rows, "sql": sql}
    finally:
        conn.close()
