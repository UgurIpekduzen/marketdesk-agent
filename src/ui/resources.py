"""What the page needs that is shared by every visitor: where the database
is, the policy index and the list of demo customers."""

import sqlite3
from pathlib import Path

from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import PolicyIndex
from src.ui.demo_customers import DemoCustomer, demo_customers

DB_PATH = Path("data/marketdesk.db")


def db_path() -> Path:
    return DB_PATH


def build_database(path: Path) -> bool:
    """Build the demo database at path unless it exists (downloads the data)."""
    # Imported here: only a page without a database needs the loader.
    from scripts.build_demo_db import ensure_database

    return ensure_database(path)


def load_policy_index() -> PolicyIndex:
    """The policy index with the real embedding model (slow the first time)."""
    return PolicyIndex(load_embedder())


def load_demo_customers(path: Path) -> list[DemoCustomer]:
    conn = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        return demo_customers(conn)
    finally:
        conn.close()
