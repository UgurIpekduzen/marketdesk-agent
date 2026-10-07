"""Check that the downloaded data and the loaded database look right.

Usage:  python scripts/smoke.py --db data/marketdesk.db

Two groups of checks:
- the raw CSV files have the row counts, order status distribution and
  distinct customers of the published Olist dataset;
- the database has the row counts expected after rule R0, the expected
  order status distribution, no order on or after SIMULATED_TODAY and no
  rows that point at a missing order.

Every check is printed. Any mismatch makes the script exit with code 1.
The database is opened read-only and is never changed.
"""

import argparse
import csv
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Run as a plain script, Python only searches the scripts/ folder for imports.
# Adding the project root lets config.py be found from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SIMULATED_TODAY

DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_DB_PATH = Path("data/marketdesk.db")


@dataclass(frozen=True)
class Expected:
    """The numbers a correct download and load must produce."""

    raw_rows: dict[str, int]  # CSV file name -> data rows
    raw_order_status: dict[str, int]  # order_status -> orders in the CSV
    raw_distinct_customers: int  # distinct customer_unique_id in the CSV
    db_rows: dict[str, int]  # table name -> rows after R0
    order_status: dict[str, int]  # order_status -> orders after R0
    distinct_customers: int  # distinct customer_unique_id after R0
    # Tables that only have to exist: the application adds rows to them.
    tables_that_exist: tuple[str, ...] = field(default=("return_requests",))


# Raw counts are those of the published dataset (version 2). Database counts
# are lower where R0 leaves out the 20 orders purchased on or after
# 2018-09-01, together with their items, payments, reviews and customers.
OLIST = Expected(
    raw_rows={
        "olist_orders_dataset.csv": 99_441,
        "olist_customers_dataset.csv": 99_441,
        "olist_order_items_dataset.csv": 112_650,
        "olist_order_payments_dataset.csv": 103_886,
        "olist_order_reviews_dataset.csv": 99_224,
        "olist_products_dataset.csv": 32_951,
        "olist_sellers_dataset.csv": 3_095,
        "olist_geolocation_dataset.csv": 1_000_163,
        "product_category_name_translation.csv": 71,
    },
    raw_order_status={
        "delivered": 96_478,
        "shipped": 1_107,
        "canceled": 625,
        "unavailable": 609,
        "invoiced": 314,
        "processing": 301,
        "created": 5,
        "approved": 2,
    },
    raw_distinct_customers=96_096,
    db_rows={
        "orders": 99_421,
        "customers": 99_421,
        "order_items": 112_649,
        "order_payments": 103_866,
        "order_reviews": 99_205,
        "products": 32_951,
        "sellers": 3_095,
        "geolocation": 1_000_163,
        "product_category_name_translation": 71,
    },
    order_status={
        "delivered": 96_478,
        "shipped": 1_106,
        "unavailable": 609,
        "canceled": 606,
        "invoiced": 314,
        "processing": 301,
        "created": 5,
        "approved": 2,
    },
    distinct_customers=96_090,
)

ORDERS_CSV = "olist_orders_dataset.csv"
CUSTOMERS_CSV = "olist_customers_dataset.csv"

# Tables whose rows must all point at an existing order.
ORDER_ID_TABLES = ("order_items", "order_payments", "order_reviews")


@dataclass(frozen=True)
class Check:
    name: str
    expected: int
    found: int

    @property
    def ok(self) -> bool:
        return self.expected == self.found

    def __str__(self) -> str:
        if self.ok:
            return f"OK    {self.name}: {self.found:,}"
        return f"FAIL  {self.name}: expected {self.expected:,}, found {self.found:,}"


def count_csv_rows(path: Path) -> int:
    """Count data rows with the csv module: some fields contain line breaks."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        next(reader, None)  # header
        return sum(1 for _ in reader)


def read_csv_column(path: Path, column: str) -> Iterator[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            yield row[column]


def raw_checks(raw_dir: Path, expected: Expected) -> list[Check]:
    checks = [
        Check(f"raw {name} rows", rows, count_csv_rows(raw_dir / name))
        for name, rows in expected.raw_rows.items()
    ]

    found_status = Counter(read_csv_column(raw_dir / ORDERS_CSV, "order_status"))
    # Union of both sides, so an unexpected status is reported as well.
    for status in sorted(expected.raw_order_status.keys() | found_status.keys()):
        checks.append(
            Check(
                f"raw orders with status {status}",
                expected.raw_order_status.get(status, 0),
                found_status.get(status, 0),
            )
        )

    customers = set(read_csv_column(raw_dir / CUSTOMERS_CSV, "customer_unique_id"))
    checks.append(
        Check(
            "raw distinct customer_unique_id",
            expected.raw_distinct_customers,
            len(customers),
        )
    )
    return checks


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def database_checks(
    conn: sqlite3.Connection, expected: Expected, simulated_today: date
) -> list[Check]:
    checks = [
        Check(f"{table} rows", rows, scalar(conn, f"SELECT COUNT(*) FROM {table}"))
        for table, rows in expected.db_rows.items()
    ]

    for table in expected.tables_that_exist:
        exists = scalar(
            conn,
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        checks.append(Check(f"{table} table exists", 1, exists))

    found_status = dict(
        conn.execute("SELECT order_status, COUNT(*) FROM orders GROUP BY order_status")
    )
    # Union of both sides, so an unexpected status is reported as well.
    for status in sorted(expected.order_status.keys() | found_status.keys()):
        checks.append(
            Check(
                f"orders with status {status}",
                expected.order_status.get(status, 0),
                found_status.get(status, 0),
            )
        )

    checks.append(
        Check(
            "distinct customer_unique_id",
            expected.distinct_customers,
            scalar(conn, "SELECT COUNT(DISTINCT customer_unique_id) FROM customers"),
        )
    )
    checks.append(
        Check(
            f"orders purchased on or after {simulated_today} (R0)",
            0,
            scalar(
                conn,
                "SELECT COUNT(*) FROM orders "
                "WHERE DATE(order_purchase_timestamp) >= DATE(?)",
                (simulated_today.isoformat(),),
            ),
        )
    )
    for table in ORDER_ID_TABLES:
        checks.append(
            Check(
                f"{table} rows without an order",
                0,
                scalar(
                    conn,
                    f"SELECT COUNT(*) FROM {table} AS child "
                    "LEFT JOIN orders ON orders.order_id = child.order_id "
                    "WHERE orders.order_id IS NULL",
                ),
            )
        )
    checks.append(
        Check(
            "customers rows without an order",
            0,
            scalar(
                conn,
                "SELECT COUNT(*) FROM customers "
                "LEFT JOIN orders ON orders.customer_id = customers.customer_id "
                "WHERE orders.order_id IS NULL",
            ),
        )
    )
    return checks


def run_checks(
    db_path: Path = DEFAULT_DB_PATH,
    raw_dir: Path = DEFAULT_RAW_DIR,
    expected: Expected = OLIST,
    simulated_today: date = SIMULATED_TODAY,
) -> list[Check]:
    """Run every check and return the results. Raises if the database is missing."""
    if not db_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {db_path}. Run the load step first."
        )

    checks: list[Check] = []
    # The raw files are not needed once the database exists (for example on
    # the deploy platform), so a missing raw folder skips that group.
    if raw_dir.is_dir():
        checks.extend(raw_checks(raw_dir, expected))

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        checks.extend(database_checks(conn, expected, simulated_today))
    finally:
        conn.close()
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args(argv)

    if not args.raw.is_dir():
        print(f"SKIP  raw CSV checks: {args.raw} not found")
    try:
        checks = run_checks(args.db, args.raw)
    except (FileNotFoundError, sqlite3.Error) as error:
        print(f"Smoke test could not run: {error}")
        return 1

    for check in checks:
        print(check)
    failed = [check for check in checks if not check.ok]
    if failed:
        print(f"Smoke test FAILED: {len(failed)} of {len(checks)} checks did not match")
        return 1
    print(f"Smoke test passed: {len(checks)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
