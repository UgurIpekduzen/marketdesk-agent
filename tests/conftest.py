"""Shared fixtures: a small synthetic database with one order per rule."""

import shutil
import sqlite3

import pytest

import config
from scripts import load_sqlite
from tests import synthetic_data
from tests.test_load_sqlite import write_raw


@pytest.fixture(scope="session")
def synthetic_db_template(tmp_path_factory):
    """Build the synthetic database once, through the real loader.

    Going through the loader keeps the schema identical to the real database
    and applies R0, so o_purchased_today is truly absent.
    """
    folder = tmp_path_factory.mktemp("synthetic")
    raw_dir = write_raw(folder / "raw", synthetic_data.build_rows())
    db_path = folder / "synthetic.db"
    load_sqlite.build_database(raw_dir, db_path, config.SIMULATED_TODAY)

    conn = sqlite3.connect(db_path)
    with conn:
        conn.executemany(
            "INSERT INTO return_requests "
            "(order_id, customer_unique_id, reason, status, created_at) "
            "VALUES (:order_id, :customer_unique_id, :reason, :status, :created_at)",
            synthetic_data.RETURN_REQUESTS,
        )
    conn.close()
    return db_path


@pytest.fixture
def synthetic_db_path(synthetic_db_template, tmp_path):
    """A private copy of the synthetic database, safe for a test to write to."""
    return shutil.copy(synthetic_db_template, tmp_path / "synthetic.db")


@pytest.fixture
def synthetic_db(synthetic_db_path):
    """An open connection to a private copy of the synthetic database."""
    conn = sqlite3.connect(synthetic_db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
