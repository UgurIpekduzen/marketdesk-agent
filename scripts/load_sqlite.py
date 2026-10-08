"""Load the Olist CSV files into a SQLite database.

Usage:  python scripts/load_sqlite.py --src data/raw --db data/marketdesk.db

What it does:
- creates one table per CSV file, with explicit column types;
- loads empty CSV cells as NULL, so the database never holds empty strings;
- applies rule R0: orders purchased on or after SIMULATED_TODAY are left
  out, together with their items, payments, reviews and customer rows;
- adds indexes on the columns used for joins and filters;
- creates the empty return_requests table, the only table the application
  writes to;
- creates the safe views, the only things free SQL may read.

The database is rebuilt from scratch on every run.
"""

import argparse
import csv
import sqlite3
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Run as a plain script, Python only searches the scripts/ folder for imports.
# Adding the project root lets config.py be found from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SIMULATED_TODAY
from src.knowledge.safe_views import create_view_statements

DEFAULT_RAW_DIR = Path("data/raw")
DEFAULT_DB_PATH = Path("data/marketdesk.db")


@dataclass(frozen=True)
class Table:
    name: str
    csv_file: str
    columns: dict[str, str]  # column name -> SQLite type, in CSV order
    primary_key: tuple[str, ...] = ()


# Column names are kept exactly as in the CSV files, typos included
# (product_name_lenght). Zip code prefixes are TEXT: they have leading zeros.
ORDERS = Table(
    name="orders",
    csv_file="olist_orders_dataset.csv",
    columns={
        "order_id": "TEXT",
        "customer_id": "TEXT",
        "order_status": "TEXT",
        "order_purchase_timestamp": "TEXT",
        "order_approved_at": "TEXT",
        "order_delivered_carrier_date": "TEXT",
        "order_delivered_customer_date": "TEXT",
        "order_estimated_delivery_date": "TEXT",
    },
    primary_key=("order_id",),
)

OTHER_TABLES = (
    Table(
        name="customers",
        csv_file="olist_customers_dataset.csv",
        columns={
            "customer_id": "TEXT",
            "customer_unique_id": "TEXT",
            "customer_zip_code_prefix": "TEXT",
            "customer_city": "TEXT",
            "customer_state": "TEXT",
        },
        primary_key=("customer_id",),
    ),
    Table(
        name="order_items",
        csv_file="olist_order_items_dataset.csv",
        columns={
            "order_id": "TEXT",
            "order_item_id": "INTEGER",
            "product_id": "TEXT",
            "seller_id": "TEXT",
            "shipping_limit_date": "TEXT",
            "price": "REAL",
            "freight_value": "REAL",
        },
        primary_key=("order_id", "order_item_id"),
    ),
    Table(
        name="order_payments",
        csv_file="olist_order_payments_dataset.csv",
        columns={
            "order_id": "TEXT",
            "payment_sequential": "INTEGER",
            "payment_type": "TEXT",
            "payment_installments": "INTEGER",
            "payment_value": "REAL",
        },
        primary_key=("order_id", "payment_sequential"),
    ),
    # No primary key: review_id is not unique in the source data.
    Table(
        name="order_reviews",
        csv_file="olist_order_reviews_dataset.csv",
        columns={
            "review_id": "TEXT",
            "order_id": "TEXT",
            "review_score": "INTEGER",
            "review_comment_title": "TEXT",
            "review_comment_message": "TEXT",
            "review_creation_date": "TEXT",
            "review_answer_timestamp": "TEXT",
        },
    ),
    Table(
        name="products",
        csv_file="olist_products_dataset.csv",
        columns={
            "product_id": "TEXT",
            "product_category_name": "TEXT",
            "product_name_lenght": "INTEGER",
            "product_description_lenght": "INTEGER",
            "product_photos_qty": "INTEGER",
            "product_weight_g": "INTEGER",
            "product_length_cm": "INTEGER",
            "product_height_cm": "INTEGER",
            "product_width_cm": "INTEGER",
        },
        primary_key=("product_id",),
    ),
    Table(
        name="sellers",
        csv_file="olist_sellers_dataset.csv",
        columns={
            "seller_id": "TEXT",
            "seller_zip_code_prefix": "TEXT",
            "seller_city": "TEXT",
            "seller_state": "TEXT",
        },
        primary_key=("seller_id",),
    ),
    Table(
        name="geolocation",
        csv_file="olist_geolocation_dataset.csv",
        columns={
            "geolocation_zip_code_prefix": "TEXT",
            "geolocation_lat": "REAL",
            "geolocation_lng": "REAL",
            "geolocation_city": "TEXT",
            "geolocation_state": "TEXT",
        },
    ),
    Table(
        name="product_category_name_translation",
        csv_file="product_category_name_translation.csv",
        columns={
            "product_category_name": "TEXT",
            "product_category_name_english": "TEXT",
        },
        primary_key=("product_category_name",),
    ),
)

TABLES = (ORDERS, *OTHER_TABLES)

# Tables whose rows belong to one order, and the column that says which.
ORDER_ID_TABLES = ("order_items", "order_payments", "order_reviews")

RETURN_REQUESTS_SQL = """
CREATE TABLE return_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    customer_unique_id TEXT NOT NULL,
    reason TEXT,
    refund_amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""

# (table, column). Primary keys already have their own index.
INDEXES = (
    ("orders", "customer_id"),
    ("orders", "order_status"),
    ("orders", "order_purchase_timestamp"),
    ("customers", "customer_unique_id"),
    ("order_items", "product_id"),
    ("order_items", "seller_id"),
    ("order_reviews", "order_id"),
    ("products", "product_category_name"),
    ("geolocation", "geolocation_zip_code_prefix"),
    ("return_requests", "order_id"),
    ("return_requests", "customer_unique_id"),
)


def read_rows(raw_dir: Path, table: Table) -> Iterator[dict[str, str | None]]:
    """Yield the rows of a table's CSV file, with empty cells as None."""
    path = raw_dir / table.csv_file
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        expected = list(table.columns)
        if reader.fieldnames != expected:
            raise ValueError(
                f"{table.csv_file}: expected columns {expected}, "
                f"found {reader.fieldnames}"
            )
        for row in reader:
            yield {column: value or None for column, value in row.items()}


def is_excluded_by_r0(purchase_timestamp: str | None, simulated_today: date) -> bool:
    """R0: an order purchased on or after the simulated today is left out.

    Dates are compared as calendar days, so the time of day is dropped.
    """
    if purchase_timestamp is None:
        return False
    return date.fromisoformat(purchase_timestamp[:10]) >= simulated_today


def create_table(conn: sqlite3.Connection, table: Table) -> None:
    definitions = [f"{column} {sql_type}" for column, sql_type in table.columns.items()]
    if table.primary_key:
        definitions.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")
    conn.execute(f"CREATE TABLE {table.name} ({', '.join(definitions)})")


def insert_rows(
    conn: sqlite3.Connection,
    table: Table,
    rows: Iterator[dict[str, str | None]],
    keep: Callable[[dict[str, str | None]], bool] = lambda row: True,
) -> int:
    """Insert the rows that pass keep() and return how many were inserted."""
    columns = list(table.columns)
    placeholders = ", ".join(f":{column}" for column in columns)
    sql = f"INSERT INTO {table.name} ({', '.join(columns)}) VALUES ({placeholders})"
    cursor = conn.executemany(sql, (row for row in rows if keep(row)))
    return cursor.rowcount


def build_database(
    raw_dir: Path = DEFAULT_RAW_DIR,
    db_path: Path = DEFAULT_DB_PATH,
    simulated_today: date = SIMULATED_TODAY,
) -> dict[str, int]:
    """Build the database from the CSV files and return rows loaded per table.

    The database is written to a temporary file first and moved into place
    only when every step has succeeded, so a failed run leaves no half-built
    database behind.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_name(db_path.name + ".tmp")
    temp_path.unlink(missing_ok=True)

    counts: dict[str, int] = {}
    conn = sqlite3.connect(temp_path)
    try:
        with conn:
            # Orders first: R0 decides which order and customer ids are left out.
            excluded_order_ids: set[str | None] = set()
            excluded_customer_ids: set[str | None] = set()

            def keep_order(row: dict[str, str | None]) -> bool:
                if is_excluded_by_r0(row["order_purchase_timestamp"], simulated_today):
                    excluded_order_ids.add(row["order_id"])
                    excluded_customer_ids.add(row["customer_id"])
                    return False
                return True

            create_table(conn, ORDERS)
            counts[ORDERS.name] = insert_rows(
                conn, ORDERS, read_rows(raw_dir, ORDERS), keep_order
            )

            def keep_dependent(table: Table) -> Callable[[dict[str, str | None]], bool]:
                """Rows of an excluded order, and its customer row, are dropped."""
                if table.name in ORDER_ID_TABLES:
                    return lambda row: row["order_id"] not in excluded_order_ids
                if table.name == "customers":
                    return lambda row: row["customer_id"] not in excluded_customer_ids
                return lambda row: True

            for table in OTHER_TABLES:
                create_table(conn, table)
                counts[table.name] = insert_rows(
                    conn, table, read_rows(raw_dir, table), keep_dependent(table)
                )

            conn.execute(RETURN_REQUESTS_SQL)
            counts["return_requests"] = 0

            for table_name, column in INDEXES:
                conn.execute(
                    f"CREATE INDEX idx_{table_name}_{column} ON {table_name} ({column})"
                )

            for statement in create_view_statements():
                conn.execute(statement)
        counts["excluded_by_r0"] = len(excluded_order_ids)
    except BaseException:
        conn.close()
        temp_path.unlink(missing_ok=True)
        raise
    conn.close()

    temp_path.replace(db_path)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--src",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help="folder that holds the nine Olist CSV files",
    )
    args = parser.parse_args()

    counts = build_database(args.src, args.db)
    excluded = counts.pop("excluded_by_r0")
    for name, count in counts.items():
        print(f"{name:<36}{count:>9,}")
    print(
        f"Orders left out by R0 (purchased on or after {SIMULATED_TODAY}): {excluded}"
    )
    print(f"Database written to {args.db}")


if __name__ == "__main__":
    main()
