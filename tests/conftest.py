"""Shared fixtures: a small synthetic database with one order per rule."""

import hashlib
import re
import shutil
import sqlite3

import numpy as np
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
            "(order_id, customer_unique_id, reason, refund_amount, status, created_at) "
            "VALUES (:order_id, :customer_unique_id, :reason, :refund_amount, "
            ":status, :created_at)",
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


class FakeEmbedder:
    """Stands in for the embedding model: no download, same interface.

    A text becomes a vector of word counts, each word (cut to its first five
    letters, to forgive Turkish endings) hashed into one of 256 slots. Texts
    that share words get similar vectors, which is all these tests need.
    """

    DIMENSIONS = 256

    def _embed(self, texts):
        vectors = np.zeros((len(texts), self.DIMENSIONS))
        for row, text in enumerate(texts):
            for word in re.findall(r"\w+", text.lower()):
                slot = int(hashlib.sha256(word[:5].encode()).hexdigest(), 16)
                vectors[row, slot % self.DIMENSIONS] += 1
            if not vectors[row].any():
                vectors[row, 0] = 1
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    embed_queries = _embed
    embed_passages = _embed


@pytest.fixture(scope="session")
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture(scope="session")
def fake_policy_index(fake_embedder, tmp_path_factory):
    """An index of the real policy sections, built with the fake embedder."""
    from src.knowledge.policy_index import PolicyIndex, build_index

    index_dir = tmp_path_factory.mktemp("policy-index") / "index"
    build_index(fake_embedder, index_dir)
    return PolicyIndex(fake_embedder, index_dir)
