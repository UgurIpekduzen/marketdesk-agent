"""Build the demo database where none exists yet.

Usage:  python -m scripts.build_demo_db [--db data/marketdesk.db]

The deployed page has no database: the Olist data may not be committed
(CC BY-NC-SA 4.0). On its first start the page downloads the dataset into a
temporary folder, loads it like `task data` does and deletes the CSV files
again. Every order stays in, so the operations answers match the evaluation;
the geolocation table is left out, because nothing reads it.
"""

import argparse
import tempfile
from pathlib import Path

from config import SIMULATED_TODAY
from data import download
from scripts.load_sqlite import DEFAULT_DB_PATH, build_database

DEMO_SKIPPED_TABLES = ("geolocation",)


def ensure_database(db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Build the demo database unless one is there; True when it was built."""
    if db_path.exists():
        return False
    with tempfile.TemporaryDirectory(prefix="olist-") as folder:
        raw_dir = download.fetch(Path(folder))
        build_database(
            raw_dir, db_path, SIMULATED_TODAY, skip_tables=DEMO_SKIPPED_TABLES
        )
    return True


def main() -> None:
    """Run the command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    if ensure_database(args.db):
        print(f"Demo database written to {args.db}")
    else:
        print(f"{args.db} exists already; nothing done")


if __name__ == "__main__":
    main()
