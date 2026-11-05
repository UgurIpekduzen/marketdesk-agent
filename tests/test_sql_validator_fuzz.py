"""The SQL validator against the real SQLite.

The validator reads a query with a parser (sqlglot); SQLite is what runs it.
Where the two read the same text differently, a query can pass the check and
then do what the check meant to stop. So every query the validator lets
through is also run on a read-only connection with SQLite's own authorizer,
which reports what the engine really touches. That is the oracle:

- at the top level only the safe views may be read (what a view reads below
  is the view's own business and is reported with the view's name);
- no function that reads or writes files, loads code or builds huge values;
- no action other than reading, calling a function and a recursive CTE.

The cases are a list chosen by hand and the same queries written differently
(case, comments, quoting, white space), with a fixed seed. A query the
validator refuses is fine; a query it passes and the oracle flags is a hole.
"""

import functools
import random
import sqlite3
import time

import pytest

import config
from src.knowledge.safe_views import ALLOWED_VIEWS
from src.knowledge.sql_runner import connect_read_only, existing_names, run_sql
from src.knowledge.sql_validator import SqlRejectedError, validate

ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}
# Functions that touch files, load code or make a huge value.
DANGEROUS_FUNCTIONS = {
    "load_extension",
    "readfile",
    "writefile",
    "edit",
    "fts3_tokenizer",
    "zeroblob",
    "randomblob",
    "sqlite_compileoption_get",
    "sqlite_compileoption_used",
    "sqlite_source_id",
    "sqlite_offset",
}

# Written by hand. The comment says what each one tries.
HAND_CASES = [
    # Other tables and the schema.
    "SELECT * FROM customers",
    "SELECT * FROM orders",
    "SELECT * FROM main.customers",
    "SELECT * FROM temp.sqlite_master",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM sqlite_schema",
    "SELECT * FROM sqlite_temp_master",
    "SELECT name FROM sqlite_master WHERE type = 'table'",
    'SELECT * FROM "customers"',
    "SELECT * FROM [customers]",
    "SELECT * FROM `customers`",
    "SELECT * FROM v_orders, customers",
    "SELECT * FROM v_orders JOIN customers ON 1",
    "SELECT * FROM v_orders WHERE order_key IN (SELECT rowid FROM customers)",
    "SELECT (SELECT customer_unique_id FROM customers LIMIT 1)",
    "WITH c AS (SELECT * FROM customers) SELECT * FROM c",
    "WITH v_orders AS (SELECT * FROM customers) SELECT * FROM v_orders",
    "SELECT * FROM v_orders UNION SELECT * FROM customers",
    "SELECT * FROM v_orders INTERSECT SELECT * FROM customers",
    "SELECT * FROM v_orders EXCEPT SELECT * FROM customers",
    # Table-valued functions and pragmas.
    "SELECT * FROM pragma_table_info('customers')",
    "SELECT * FROM pragma_database_list",
    "SELECT * FROM pragma_function_list",
    "SELECT * FROM json_each('[1,2,3]')",
    "SELECT * FROM json_tree('{\"a\":1}')",
    "SELECT * FROM generate_series(1, 5)",
    "SELECT * FROM dbstat",
    "SELECT * FROM sqlite_dbpage",
    # Functions with side effects or reach.
    "SELECT load_extension('/tmp/x')",
    "SELECT readfile('/etc/passwd')",
    "SELECT writefile('/tmp/x', 'x')",
    "SELECT fts3_tokenizer('x')",
    "SELECT sqlite_version()",
    "SELECT sqlite_source_id()",
    "SELECT sqlite_compileoption_used('X')",
    "SELECT hex(zeroblob(100000000))",
    "SELECT length(zeroblob(1000000000))",
    "SELECT length(randomblob(1000000000))",
    "SELECT printf('%.*c', 100000000, 'x')",
    "SELECT length(replace(hex(zeroblob(50000000)), '0', 'ab'))",
    "SELECT group_concat(hex(randomblob(100000)))",
    "SELECT random()",
    "SELECT abs(random())",
    "SELECT sqlite_offset(order_key) FROM v_orders",
    "SELECT * FROM v_orders WHERE order_key = load_extension('x')",
    # Statements other than SELECT.
    "ATTACH DATABASE ':memory:' AS x",
    "ATTACH DATABASE '/tmp/x.db' AS x; SELECT 1",
    "PRAGMA table_info(customers)",
    "PRAGMA writable_schema = 1",
    "VACUUM",
    "VACUUM INTO '/tmp/x.db'",
    "ANALYZE",
    "REINDEX",
    "BEGIN; SELECT 1; COMMIT",
    "SELECT 1; SELECT 2",
    "SELECT 1; DROP TABLE customers",
    "EXPLAIN SELECT * FROM v_orders",
    "EXPLAIN QUERY PLAN SELECT * FROM v_orders",
    "INSERT INTO return_requests DEFAULT VALUES",
    "UPDATE v_orders SET order_status = 'x'",
    "DELETE FROM v_orders",
    "CREATE TABLE t (a)",
    "CREATE TEMP TABLE t AS SELECT * FROM v_orders",
    "DROP VIEW v_orders",
    "SELECT * FROM v_orders; --",
    "REPLACE INTO return_requests DEFAULT VALUES",
    "WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x",
    "WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x",
    # Resource use.
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT n FROM r",
    (
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r "
        "LIMIT 100000000) SELECT count(*) FROM r"
    ),
    "SELECT count(*) FROM v_orders a, v_orders b, v_orders c, v_orders d",
    "SELECT * FROM v_orders WHERE order_status LIKE '%' || '%' || '%' || '%' || '%'",
    "SELECT * FROM v_orders ORDER BY random()",
    # Text the parser may read differently from the engine.
    "SELECT * FROM v_orders /* ; DROP TABLE customers */",
    "SELECT * FROM v_orders -- ; DROP TABLE customers\n",
    "SELECT * FROM v_orders WHERE order_status = 'x'' OR 1=1 --'",
    'SELECT * FROM v_orders WHERE order_status = "customers"',
    "SELECT 'a' || x'41' FROM v_orders",
    "SELECT * FROM v_orders WHERE 1 = 1 UNION SELECT * FROM v_orders",
    "SELECT * FROM v_orders\x00; DROP TABLE customers",
    "SELECT * FROM v_orders\f",
    "SELECT * FROM v_orders",
    "SELECT * FROM v_orders AS customers",
    "SELECT customers.* FROM v_orders AS customers",
    "SELECT * FROM v_orders LIMIT -1",
    "SELECT * FROM v_orders LIMIT 999999999999",
    "SELECT * FROM v_orders LIMIT 1 OFFSET 99999999999",
    "SELECT * FROM (SELECT * FROM v_orders) AS t",
    "SELECT * FROM (SELECT * FROM customers) AS t",
    "SELECT * FROM v_orders NATURAL JOIN v_order_items",
    "SELECT * FROM v_orders INDEXED BY x",
    "SELECT * FROM v_orders NOT INDEXED",
    "SELECT * FROM v_orders WHERE order_key IN (SELECT order_key FROM v_order_items)",
    "SELECT json_extract('{\"a\":1}', '$.a')",
    "SELECT * FROM v_orders WHERE order_key MATCH 'x'",
    "SELECT * FROM v_orders WHERE order_status GLOB '*'",
    "SELECT * FROM v_orders WHERE order_status REGEXP 'x'",
]


def authorize_of_authorizer_into(seen, action, first, second, database, source):
    seen.append((action, first, second, database, source))
    return sqlite3.SQLITE_OK


def authorizer_into(seen: list):

    return functools.partial(authorize_of_authorizer_into, seen)


def holes(conn: sqlite3.Connection, sql: str) -> list[str]:
    """What the engine does with a query that the oracle's policy forbids."""
    real = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    seen: list = []
    conn.set_authorizer(authorizer_into(seen))
    try:
        # Prepare the query only: the authorizer is asked while it is compiled.
        conn.execute(f"EXPLAIN {sql}").fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.set_authorizer(None)

    found = []
    for action, first, second, _database, source in seen:
        if action not in ALLOWED_ACTIONS:
            found.append(f"action {action}")
        elif (
            action == sqlite3.SQLITE_READ
            and source is None
            and first in real
            and first not in ALLOWED_VIEWS
        ):
            found.append(f"reads {first}")
        elif (
            action == sqlite3.SQLITE_FUNCTION
            and (second or "").lower() in DANGEROUS_FUNCTIONS
        ):
            found.append(f"function {second}")
    return found


@pytest.fixture
def engine(synthetic_db_path):
    conn = connect_read_only(synthetic_db_path)
    yield conn, existing_names(conn)
    conn.close()


def passed(query: str, names: tuple[str, ...]) -> str | None:
    """The SQL the validator would run, or None when it refuses the query."""
    try:
        return validate(query, names)
    except SqlRejectedError:
        return None


# --- The hand-picked cases ------------------------------------------------


def test_passed_queries_satisfy_the_oracle(engine):
    conn, names = engine
    problems = {}
    for query in HAND_CASES:
        sql = passed(query, names)
        if sql is not None and (found := holes(conn, sql)):
            problems[query] = found

    assert problems == {}


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM customers",
        "SELECT * FROM sqlite_master",
        "SELECT * FROM main.customers",
        "SELECT * FROM pragma_table_info('customers')",
        "SELECT readfile('/etc/passwd')",
        "SELECT load_extension('x')",
        "ATTACH DATABASE ':memory:' AS x",
        "PRAGMA table_info(customers)",
        "SELECT 1; SELECT 2",
        "INSERT INTO return_requests DEFAULT VALUES",
        "CREATE TABLE t (a)",
        "WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x",
        "WITH v_orders AS (SELECT * FROM customers) SELECT * FROM v_orders",
        "SELECT * FROM v_orders UNION SELECT * FROM customers",
    ],
)
def test_the_clearly_forbidden_are_refused(engine, query):
    _, names = engine

    assert passed(query, names) is None


def test_list_has_refused_and_passed_cases(engine):
    _, names = engine
    refused = [q for q in HAND_CASES if passed(q, names) is None]
    let_through = [q for q in HAND_CASES if passed(q, names) is not None]

    # The list is not trivial in either direction: it tries things the
    # validator stops and things it lets through that are harmless.
    assert len(refused) > 40
    assert len(let_through) >= 5


# --- The same queries written differently ---------------------------------


def rewrite(query: str, rng: random.Random) -> str:
    """One query written another way; the meaning is meant to stay."""
    tokens = query.split(" ")
    out = []
    for token in tokens:
        choice = rng.random()
        if choice < 0.12:
            token = token.upper()
        elif choice < 0.24:
            token = token.lower()
        elif choice < 0.30:
            token = token + "/**/"
        elif choice < 0.34:
            token = "/*" + "x" * rng.randint(0, 5) + "*/" + token
        out.append(token)
    separators = [" ", " ", "  ", "\t", "\n", "\r\n", "\f", " /**/ "]
    text = ""
    for i, token in enumerate(out):
        text += token + (rng.choice(separators) if i < len(out) - 1 else "")
    for view in ALLOWED_VIEWS:
        if view in text and rng.random() < 0.25:
            text = text.replace(
                view,
                rng.choice([f'"{view}"', f"[{view}]", f"`{view}`", f"main.{view}"]),
            )
    if rng.random() < 0.15:
        text += rng.choice([";", " ;", "; --", "\n--", " /* end */"])
    return text


def test_rewritten_queries_satisfy_oracle(engine):
    conn, names = engine
    rng = random.Random(20261024)
    problems = {}
    let_through = 0
    for query in HAND_CASES * 12:
        variant = rewrite(query, rng)
        sql = passed(variant, names)
        if sql is None:
            continue
        let_through += 1
        if found := holes(conn, sql):
            problems[variant] = found

    assert let_through > 50
    assert problems == {}


# --- What runs, runs inside its limits ------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        (
            "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) "
            "SELECT count(*) FROM r"
        ),
        (
            "SELECT count(*) FROM v_orders a, v_orders b, v_orders c, "
            "v_orders d, v_orders e, v_orders f"
        ),
        "SELECT length(printf('%.*c', 900000000, 'x'))",
        "SELECT length(replace(hex(zeroblob(50000000)), '0', 'ab'))",
    ],
)
def test_heavy_query_ends_by_timeout(synthetic_db_path, query):
    started = time.monotonic()
    answer = run_sql(synthetic_db_path, query, timeout_seconds=2.0)
    spent = time.monotonic() - started

    assert spent < 6.0
    assert answer.get("error") in {"SQL_REJECTED", "SQL_TIMEOUT", "SQL_ERROR", None}


# --- Holes this file found, and their fixes ---------------------------------


def test_one_query_cannot_build_huge_values(
    synthetic_db_path,
):
    answer = run_sql(synthetic_db_path, "SELECT length(format('%.*c', 400000000, 'x'))")

    # The engine builds nothing: the value is NULL (or the call is an error).
    assert answer.get("rows") in (None, [[None]])
    assert answer.get("error") in (None, "SQL_ERROR")
    assert answer.get("rows") is not None or "too big" in answer["detail"]


def test_nesting_respects_the_value_limit(synthetic_db_path):
    answer = run_sql(
        synthetic_db_path,
        "SELECT length(replace(replace(format('%.*c', 90000, 'x'), 'x', 'yy'), "
        "'y', 'zzzz'))",
    )

    assert answer.get("rows") in (None, [[None]])
    assert answer.get("error") in (None, "SQL_ERROR")


def test_small_values_cannot_sum_to_huge(
    synthetic_db_path,
):
    # 1,000 rows of 90,000 characters: each value passes, the answer is 90 MB.
    answer = run_sql(
        synthetic_db_path,
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL "
        "SELECT n + 1 FROM r WHERE n < 1000) "
        "SELECT format('%.*c', 90000, 'x') AS big FROM r",
    )

    assert answer["error"] == "SQL_ERROR"
    assert answer["detail"] == "RESULT_TOO_LARGE"
    assert "rows" not in answer


def test_ordinary_answer_ignores_the_limits(synthetic_db_path):
    answer = run_sql(
        synthetic_db_path,
        "SELECT order_status, count(*) AS orders FROM v_orders GROUP BY order_status",
    )

    assert "error" not in answer
    assert answer["rows"]


def test_the_connection_carries_the_limits(synthetic_db_path):
    conn = connect_read_only(synthetic_db_path)
    try:
        assert conn.getlimit(sqlite3.SQLITE_LIMIT_LENGTH) == config.SQL_MAX_VALUE_BYTES
        assert conn.getlimit(sqlite3.SQLITE_LIMIT_ATTACHED) == 0
        heap = conn.execute("PRAGMA hard_heap_limit").fetchone()[0]
        assert heap == config.SQL_HEAP_LIMIT_BYTES
    finally:
        conn.close()


def test_the_engine_version_is_not_readable(synthetic_db_path):
    answer = run_sql(synthetic_db_path, "SELECT sqlite_version()")

    assert answer["error"] == "SQL_REJECTED"
    assert answer["reason"] == "FUNCTION_NOT_ALLOWED"
