"""Tests for the embedding code, with a stand-in model: no download needed.

The stand-in gives every token the vector [token id, 1], so the expected
result of the pooling can be worked out by hand.
"""

from types import SimpleNamespace

import numpy as np
import pytest

import config
from src.knowledge.embedding import PASSAGE_PREFIX, QUERY_PREFIX, Embedder

PAD = 0


class FakeTokenizer:
    """One token per word; the token id is the length of the word."""

    def __init__(self):
        self.seen = []

    def encode_batch(self, texts):
        self.seen.append(list(texts))
        rows = [[len(word) for word in text.split()] for text in texts]
        width = max(len(row) for row in rows)
        return [
            SimpleNamespace(
                ids=row + [PAD] * (width - len(row)),
                attention_mask=[1] * len(row) + [0] * (width - len(row)),
            )
            for row in rows
        ]


class FakeSession:
    def __init__(self, input_names=("input_ids", "attention_mask")):
        self.input_names = input_names
        self.feeds = []

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.input_names]

    def run(self, output_names, input_feed):
        self.feeds.append(input_feed)
        ids = input_feed["input_ids"].astype(float)
        # Padding gets a large vector on purpose: pooling must ignore it.
        first = np.where(input_feed["attention_mask"] == 1, ids, 1000.0)
        return [np.stack([first, np.ones_like(ids)], axis=-1)]


@pytest.fixture
def parts():
    return FakeSession(), FakeTokenizer()


def test_queries_get_the_query_prefix(parts):
    session, tokenizer = parts

    Embedder(session, tokenizer).embed_queries(["iade süresi", "kargo"])

    assert tokenizer.seen == [[QUERY_PREFIX + "iade süresi", QUERY_PREFIX + "kargo"]]


def test_passages_get_the_passage_prefix(parts):
    session, tokenizer = parts

    Embedder(session, tokenizer).embed_passages(["İade süresi 14 gündür."])

    assert tokenizer.seen == [[PASSAGE_PREFIX + "İade süresi 14 gündür."]]


def test_prefixes_are_the_ones_e5_expects():
    assert (QUERY_PREFIX, PASSAGE_PREFIX) == ("query: ", "passage: ")


def test_one_unit_row_per_text(parts):
    vectors = Embedder(*parts).embed_queries(["bir", "iki kelime", "üç ayrı kelime"])

    assert vectors.shape == (3, 2)
    assert np.linalg.norm(vectors, axis=1) == pytest.approx([1.0, 1.0, 1.0])


def test_pooling_averages_skips_padding(parts):
    # "query: ab abcd" -> ids 6, 2, 4 (mean 4); "query: a" -> ids 6, 1 + padding
    # (mean 3.5). The second column is 1 for every token.
    vectors = Embedder(*parts).embed_queries(["ab abcd", "a"])

    expected = np.array([[4.0, 1.0], [3.5, 1.0]])
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    assert vectors == pytest.approx(expected)


def test_vector_same_alone_and_in_batch(parts):
    embedder = Embedder(*parts)

    alone = embedder.embed_queries(["a"])
    in_batch = embedder.embed_queries(["a", "çok daha uzun bir soru cümlesi"])

    assert alone[0] == pytest.approx(in_batch[0])


def test_model_gets_ids_and_mask_as_integers(parts):
    session, tokenizer = parts

    Embedder(session, tokenizer).embed_queries(["iki kelime"])

    feed = session.feeds[0]
    assert set(feed) == {"input_ids", "attention_mask"}
    assert feed["input_ids"].dtype == np.int64
    assert feed["attention_mask"].dtype == np.int64


def test_token_type_ids_only_when_wanted():
    session = FakeSession(("input_ids", "attention_mask", "token_type_ids"))

    Embedder(session, FakeTokenizer()).embed_queries(["iki kelime"])

    feed = session.feeds[0]
    assert feed["token_type_ids"].shape == feed["input_ids"].shape
    assert not feed["token_type_ids"].any()


def test_model_is_pinned_to_a_revision():
    assert len(config.EMBEDDING_MODEL_REVISION) == 40
    assert config.EMBEDDING_MODEL_FILE.endswith(".onnx")
    assert config.EMBEDDING_DIMENSIONS == 384
