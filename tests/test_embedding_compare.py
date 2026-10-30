"""Tests for the embedding model comparison: how a text becomes a vector for
each kind of model, how a rank is counted, and what the report says. No model,
no network."""

import re
from types import SimpleNamespace

import numpy as np
import pytest

import config
from eval import embedding_compare as compare
from eval.embedding_compare import MODELS, count_found, embed, rank_of_expected


class FakeTokenizer:
    """Words become ids; shorter rows are padded with id 0 and mask 0."""

    def __init__(self):
        self.seen = []

    def encode_batch(self, texts):
        self.seen.extend(texts)
        rows = [[len(word) for word in text.split()] for text in texts]
        width = max(len(row) for row in rows)
        return [
            SimpleNamespace(
                ids=row + [0] * (width - len(row)),
                attention_mask=[1] * len(row) + [0] * (width - len(row)),
            )
            for row in rows
        ]


class FakeSession:
    """Every token id t becomes the vector [t, 1]; padding becomes [0, 1]."""

    def get_inputs(self):
        return [
            SimpleNamespace(name="input_ids"),
            SimpleNamespace(name="attention_mask"),
        ]

    def run(self, output_names, feed):
        ids = feed["input_ids"].astype(float)
        return [np.stack([ids, np.ones_like(ids)], axis=-1)]


def unit(vector):
    vector = np.array(vector, dtype=float)
    return vector / np.linalg.norm(vector)


def test_mean_pooling_skips_padding():
    # "aa bbbb" -> ids 2, 4 -> mean [3, 1]; the padded row must not be pulled
    # towards zero by its padding.
    vectors = embed(FakeTokenizer(), FakeSession(), ["aa bbbb", "cccccc"], "mean")

    assert vectors[0] == pytest.approx(unit([3, 1]))
    assert vectors[1] == pytest.approx(unit([6, 1]))


def test_cls_pooling_takes_first_token():
    vectors = embed(FakeTokenizer(), FakeSession(), ["aa bbbb", "cccccc"], "cls")

    assert vectors[0] == pytest.approx(unit([2, 1]))
    assert vectors[1] == pytest.approx(unit([6, 1]))


def test_vectors_have_unit_length():
    vectors = embed(FakeTokenizer(), FakeSession(), ["a bb", "ccc"], "mean")

    assert np.linalg.norm(vectors, axis=1) == pytest.approx([1, 1])


def test_batches_give_the_same_rows():
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]
    whole = compare.embed_in_batches(FakeTokenizer(), FakeSession(), texts, "mean", 5)
    parts = compare.embed_in_batches(FakeTokenizer(), FakeSession(), texts, "mean", 2)

    assert parts.shape == whole.shape == (5, 2)
    assert parts == pytest.approx(whole)


def test_rank_is_best_expected_section():
    keys = [("a", 1), ("b", 1), ("c", 1)]
    scores = np.array([0.2, 0.9, 0.5])

    assert rank_of_expected(scores, keys, [("b", 1)]) == 1
    assert rank_of_expected(scores, keys, [("c", 1), ("a", 1)]) == 2
    assert rank_of_expected(scores, keys, [("a", 1)]) == 3


def test_found_counts_use_the_thresholds():
    found = count_found([1, 2, 3, 4, 5, 6, 1])

    assert (found["first"], found["top3"], found["top5"]) == (2, 4, 6)


def test_mrr_and_worst_rank():
    found = count_found([1, 2, 4])

    assert found["mrr"] == pytest.approx((1 + 1 / 2 + 1 / 4) / 3, abs=0.001)
    assert found["worst"] == 4
    assert count_found([1, 1])["mrr"] == 1


def test_e5_models_get_prefixes_bge_none():
    for name in ("e5-small", "e5-base"):
        assert MODELS[name].query_prefix == "query: "
        assert MODELS[name].passage_prefix == "passage: "
        assert MODELS[name].pooling == "mean"
    assert MODELS["bge-m3"].query_prefix == MODELS["bge-m3"].passage_prefix == ""
    assert MODELS["bge-m3"].pooling == "cls"


def test_measure_adds_the_prefixes():
    spec = MODELS["e5-small"]
    tokenizer = FakeTokenizer()
    sections = [
        SimpleNamespace(file="a", number=1, embedding_text="alpha beta"),
        SimpleNamespace(file="b", number=1, embedding_text="gamma"),
    ]

    result = compare.measure(
        spec, tokenizer, FakeSession(), sections, [("R1", "alpha?", [("a", 1)])], 10
    )

    assert "passage: alpha beta" in tokenizer.seen
    assert "query: alpha?" in tokenizer.seen
    assert result["dimensions"] == 2
    assert result["per_question"][0]["expected"] == [["a", 1]]
    assert result["per_question"][0]["rank"] in (1, 2)


def test_every_revision_is_pinned():
    for spec in MODELS.values():
        assert re.fullmatch(r"[0-9a-f]{40}", spec.revision), spec.name


def test_baseline_is_the_product_model():
    small = MODELS["e5-small"]

    assert small.repo == config.EMBEDDING_MODEL_REPO
    assert small.revision == config.EMBEDDING_MODEL_REVISION


def test_report_shows_every_batch_way():
    def run(first, top3):
        return {
            "dimensions": 384,
            "first": first,
            "top3": top3,
            "top5": 18,
            "mrr": 0.8,
            "worst": 8,
            "query_ms_p50": 2.5,
        }

    results = {
        "e5-small": {
            "repo": "r/small",
            "revision": "x" * 40,
            "sections": 28,
            "questions": 20,
            "peak_memory_mb": 651,
            "by_batch_size": {
                "all": run(14, 18),
                "10": run(14, 17),
                "1": run(15, 17),
            },
        }
    }

    text = compare.markdown(results)

    assert (
        "| e5-small | 384 | 14 / 14 / 15 | 18 / 17 / 17 | 18 | 0.8 | 8 | 2.5 | 651 |"
        in text
    )
    assert "`r/small` at `" + "x" * 40 + "`" in text
    assert "20 questions, 28 policy sections" in text
