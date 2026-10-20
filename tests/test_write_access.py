"""Tests for the least-privilege connections: reading is free, writing is
limited to what is listed, and SQLite itself refuses the rest."""

import hashlib
import sqlite3

import pytest

from src.guardrails.write_access import restrict_writes


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "shop.db"
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("CREATE TABLE orders (id TEXT, status TEXT)")
        conn.execute("INSERT INTO orders VALUES ('o1', 'delivered')")
        conn.execute(
            "CREATE TABLE return_requests "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, status TEXT, refund_amount REAL)"
        )
        conn.execute(
            "INSERT INTO return_requests (status, refund_amount) VALUES ('A', 9)"
        )
    conn.close()
    return path


def content(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restricted(path, **lists):
    return restrict_writes(sqlite3.connect(path), **lists)


def write(conn, sql: str) -> None:
    with conn:
        conn.execute(sql)


def test_reading_is_allowed_everywhere(db_path):
    conn = restricted(db_path)

    assert conn.execute("SELECT id FROM orders").fetchall() == [("o1",)]
    assert conn.execute(
        "WITH n AS (SELECT DATE('2018-09-01') AS d) SELECT d FROM n"
    ).fetchone() == ("2018-09-01",)


def test_a_listed_table_takes_new_rows(db_path):
    conn = restricted(db_path, inserts=["return_requests"])

    write(conn, "INSERT INTO return_requests (status, refund_amount) VALUES ('B', 1)")

    assert conn.execute("SELECT COUNT(*) FROM return_requests").fetchone() == (2,)


def test_a_listed_column_can_be_changed_and_no_other(db_path):
    conn = restricted(db_path, updates=[("return_requests", "status")])

    write(conn, "UPDATE return_requests SET status = 'C' WHERE id = 1")
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        write(conn, "UPDATE return_requests SET refund_amount = 1000 WHERE id = 1")

    assert conn.execute(
        "SELECT status, refund_amount FROM return_requests"
    ).fetchone() == (
        "C",
        9,
    )


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO orders VALUES ('o2', 'x')",
        "UPDATE orders SET status = 'canceled'",
        "UPDATE return_requests SET status = 'X'",
        "DELETE FROM return_requests",
        "DELETE FROM orders",
        "DROP TABLE orders",
        "CREATE TABLE copy AS SELECT * FROM orders",
        "ALTER TABLE orders ADD COLUMN note TEXT",
        "CREATE INDEX i ON orders (id)",
        "PRAGMA table_info(orders)",
        "ATTACH DATABASE ':memory:' AS other",
    ],
)
def test_everything_not_listed_is_refused_and_changes_nothing(db_path, sql):
    before = content(db_path)
    conn = restricted(db_path, inserts=["return_requests"])

    with pytest.raises(sqlite3.DatabaseError):
        write(conn, sql)
    conn.close()

    assert content(db_path) == before


def test_names_are_matched_in_any_case(db_path):
    conn = restricted(db_path, inserts=["RETURN_REQUESTS"])

    write(conn, "insert into Return_Requests (status) values ('D')")
