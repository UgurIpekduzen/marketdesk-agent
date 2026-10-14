"""Tests for scripts/build_demo_db.py. No network: the download is replaced
by a folder of tiny synthetic CSV files."""

import sqlite3

import pytest

from scripts import build_demo_db
from tests.test_load_sqlite import write_raw


@pytest.fixture
def fake_fetch(monkeypatch):
    """Stand in for the download: write the CSV files into the given folder."""
    folders = []

    def fetch(output_dir):
        folders.append(output_dir)
        return write_raw(output_dir / "csv")

    monkeypatch.setattr(build_demo_db.download, "fetch", fetch)
    return folders


def tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        conn.close()


def test_builds_the_database_without_the_geolocation_table(fake_fetch, tmp_path):
    db_path = tmp_path / "data" / "marketdesk.db"

    assert build_demo_db.ensure_database(db_path) is True

    assert "orders" in tables(db_path)
    assert "return_requests" in tables(db_path)
    assert "geolocation" not in tables(db_path)


def test_the_downloaded_files_are_deleted_afterwards(fake_fetch, tmp_path):
    build_demo_db.ensure_database(tmp_path / "marketdesk.db")

    (folder,) = fake_fetch
    assert not folder.exists()


def test_an_existing_database_is_left_alone(fake_fetch, tmp_path):
    db_path = tmp_path / "marketdesk.db"
    db_path.write_bytes(b"already here")

    assert build_demo_db.ensure_database(db_path) is False

    assert fake_fetch == []
    assert db_path.read_bytes() == b"already here"


def test_a_failed_download_leaves_no_database(monkeypatch, tmp_path):
    def fail(output_dir):
        raise OSError("network is down")

    monkeypatch.setattr(build_demo_db.download, "fetch", fail)
    db_path = tmp_path / "marketdesk.db"

    with pytest.raises(OSError, match="network is down"):
        build_demo_db.ensure_database(db_path)

    assert not db_path.exists()
