"""Checks a free SQL query before it is run.

The query is parsed into a tree with a real SQL parser, and the checks walk
the whole tree, not only its top: a forbidden statement hidden in a CTE or
a raw table named in a subquery is found the same way.

A query passes only if it is:

1. one statement,
2. a SELECT (also WITH ... SELECT, and UNION and the like of SELECTs),
3. free of anything that writes, changes the schema, or is not understood
   (INSERT, UPDATE, DELETE, DROP, ALTER, ATTACH, PRAGMA, ...),
4. reading only from the allowed views, or from CTEs it defines itself,
5. calling no function outside the parser's known ones and a short list.

The SQL that is run is written out again from the checked tree, with the
row limit set, so what runs is exactly what was checked.
"""

import sqlglot
from sqlglot import errors, exp

import config
from src.knowledge.safe_views import ALLOWED_VIEWS

DIALECT = "sqlite"

# Statement kinds that may never appear anywhere in the tree. Command is
# what the parser returns for a statement it does not understand.
FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Into,
    exp.Attach,
    exp.Detach,
    exp.Pragma,
    exp.Command,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Set,
    exp.Use,
    exp.Copy,
    exp.Analyze,
)

# Functions the parser has no class for are refused, except these: SQLite's
# date and time functions and TOTAL.
ALLOWED_EXTRA_FUNCTIONS = ("julianday", "datetime", "time", "unixepoch", "total")


class SqlRejected(Exception):
    """A query that failed a check. code is fixed; detail names the culprit."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def is_select(node: exp.Expression) -> bool:
    return isinstance(node, (exp.Select, exp.SetOperation))


def parse_single_statement(query: str) -> exp.Expression:
    try:
        statements = sqlglot.parse(query, read=DIALECT)
    except errors.SqlglotError as error:
        raise SqlRejected("PARSE_ERROR", str(error).splitlines()[0]) from error
    # A trailing ";" or comment leaves an empty statement behind.
    statements = [
        statement
        for statement in statements
        if statement is not None and not isinstance(statement, exp.Semicolon)
    ]
    if not statements:
        raise SqlRejected("EMPTY_QUERY")
    if len(statements) > 1:
        raise SqlRejected("MULTIPLE_STATEMENTS")
    return statements[0]


def check_tree(
    tree: exp.Expression,
    allowed_tables: tuple[str, ...],
    reserved_names: tuple[str, ...],
) -> None:
    if not is_select(tree):
        raise SqlRejected("NOT_A_SELECT", tree.key.upper())

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlRejected("FORBIDDEN_STATEMENT", node.key.upper())

    # A CTE may not take the name of anything that exists in the database:
    # outside the CTE's reach the same name would mean the real table.
    reserved = {name.lower() for name in (*reserved_names, *allowed_tables)}
    cte_names = set()
    for cte in tree.find_all(exp.CTE):
        name = cte.alias.lower()
        if not is_select(cte.this):
            raise SqlRejected("FORBIDDEN_STATEMENT", cte.this.key.upper())
        if name in reserved or name.startswith("sqlite_"):
            raise SqlRejected("TABLE_NOT_ALLOWED", cte.alias)
        cte_names.add(name)

    allowed = {name.lower() for name in allowed_tables} | cte_names
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            # A function used as a table, such as pragma_table_info(...).
            raise SqlRejected("TABLE_NOT_ALLOWED", table.sql(dialect=DIALECT))
        if table.db or table.catalog or table.name.lower() not in allowed:
            raise SqlRejected("TABLE_NOT_ALLOWED", table.sql(dialect=DIALECT))

    for function in tree.find_all(exp.Anonymous):
        if function.name.lower() not in ALLOWED_EXTRA_FUNCTIONS:
            raise SqlRejected("FUNCTION_NOT_ALLOWED", function.name)


def with_row_limit(tree: exp.Expression, max_rows: int) -> exp.Expression:
    """Keep a LIMIT from 0 to max_rows; set max_rows in every other case."""
    limit = tree.args.get("limit")
    if limit is not None:
        count = limit.expression
        if (
            isinstance(count, exp.Literal)
            and count.is_int
            and 0 <= int(count.this) <= max_rows
        ):
            return tree
    return tree.limit(max_rows)


def validate(
    query: str,
    reserved_names: tuple[str, ...],
    allowed_tables: tuple[str, ...] = ALLOWED_VIEWS,
    max_rows: int = config.SQL_MAX_ROWS,
) -> str:
    """Return the SQL to run for a query, or raise SqlRejected.

    reserved_names are the names of everything that exists in the database
    (tables, views, indexes); a CTE may not reuse one of them.
    """
    tree = parse_single_statement(query)
    check_tree(tree, allowed_tables, reserved_names)
    sql = with_row_limit(tree, max_rows).sql(dialect=DIALECT)

    # The SQL was written out again from the tree; check that text as well,
    # so nothing changed its meaning on the way out.
    check_tree(parse_single_statement(sql), allowed_tables, reserved_names)
    return sql
