"""Least privilege for the two connections that write to the database.

The order server writes new return requests and tickets; the support rep
console changes their status. Their code writes nothing else, but a plain
SQLite connection would let it write every table, raw Olist data included.
restrict_writes() hands the connection to SQLite's authorizer with a list
of what is allowed, so a write outside the list fails in SQLite itself,
whatever the code above it does:

- reading is allowed everywhere;
- inserts only into the tables named in `inserts`;
- updates only of the (table, column) pairs named in `updates`;
- everything else is refused: DELETE, DROP, CREATE, ALTER, ATTACH, PRAGMA,
  and any insert or update not on the lists.

Tables the connection needs are created before it is restricted.
"""

import sqlite3
from collections.abc import Iterable

# Actions that only read, or that frame the allowed writes.
ALWAYS_ALLOWED = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_SAVEPOINT,
}


class WriteAllowlist:
    """What SQLite asks before it runs a statement: reading is free, inserting only
    into the listed tables and updating only the listed columns."""

    def __init__(
        self, inserts: Iterable[str], updates: Iterable[tuple[str, str]]
    ) -> None:
        self.inserts = {table.lower() for table in inserts}
        self.updates = {(table.lower(), column.lower()) for table, column in updates}

    def authorize(self, action, first, second, database, source):
        """SQLite authorizer: allow reads and the listed writes, deny the rest.

        Args:
            action: The SQLite action code.
            first: The first argument of the action, often a table name.
            second: The second argument, often a column name.
            database: The database name.
            source: The trigger or view that asked, if any.

        Returns:
            SQLITE_OK to allow the action, SQLITE_DENY otherwise.
        """
        if action in ALWAYS_ALLOWED:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_INSERT and (first or "").lower() in self.inserts:
            return sqlite3.SQLITE_OK
        if (
            action == sqlite3.SQLITE_UPDATE
            and ((first or "").lower(), (second or "").lower()) in self.updates
        ):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY


def restrict_writes(
    conn: sqlite3.Connection,
    inserts: Iterable[str] = (),
    updates: Iterable[tuple[str, str]] = (),
) -> sqlite3.Connection:
    """Let the connection read anything and write only what is listed.

    Args:
        conn (sqlite3.Connection): The connection to restrict.
        inserts (Iterable[str]): The tables rows may be inserted into.
        updates (Iterable[tuple[str, str]]): The (table, column) pairs that may be
            updated.

    Returns:
        The same connection, now restricted.
    """
    conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    conn.set_authorizer(WriteAllowlist(inserts, updates).authorize)
    return conn
