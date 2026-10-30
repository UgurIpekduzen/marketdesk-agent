"""Tests for the comparison of the policy search through LlamaIndex with
direct Chroma: that the direct version answers like the product's, that the
comparison notices a difference, and what the report says. A stand-in for the
embedding model: no download, no network."""

from eval import index_compare as compare
from eval.index_compare import DirectIndex, build_direct, compare_answers
from src.knowledge.policy_index import PolicyIndex, build_index, read_sections
from tests.fakes import FakeEmbedder
from tests.retrieval_questions import QUESTIONS


def both_indexes(tmp_path):
    embedder = FakeEmbedder()
    build_direct(embedder, read_sections(), tmp_path / "direct")
    build_index(embedder, tmp_path / "llama")
    return (
        DirectIndex(embedder, tmp_path / "direct"),
        PolicyIndex(embedder, tmp_path / "llama"),
    )


def result(document, section, score):
    return {"document": document, "section": section, "score": score}


def test_both_give_the_same_top_sections(tmp_path):
    direct, llama = both_indexes(tmp_path)

    for _, question, _ in QUESTIONS:
        verdict = compare_answers(direct.search(question, 5), llama.search(question, 5))
        assert verdict["same_sections"], question
        assert verdict["max_score_gap"] < 0.001, question


def test_direct_result_has_the_product_shape(tmp_path):
    direct, llama = both_indexes(tmp_path)

    found = direct.search("iade süresi", 3)

    assert len(found) == 3
    assert found[0].keys() == llama.search("iade süresi", 3)[0].keys()
    assert found[0]["score"] >= found[1]["score"] >= found[2]["score"]


def test_a_different_order_is_noticed():
    first = [result("A", 1, 0.9), result("B", 2, 0.8)]
    second = [result("B", 2, 0.8), result("A", 1, 0.9)]

    assert compare_answers(first, first)["same_sections"]
    assert not compare_answers(first, second)["same_sections"]


def test_score_gap_is_the_largest_one():
    first = [result("A", 1, 0.9), result("B", 2, 0.8)]
    second = [result("A", 1, 0.8999), result("B", 2, 0.7)]

    assert compare_answers(first, second)["max_score_gap"] == 0.1


def test_span_gives_one_value_when_equal():
    assert compare.span([2.0, 2.0]) == "2.0"
    assert compare.span([2.0, 3.5]) == "2.0–3.5"


def test_whole_run_agrees_on_every_question():
    outcome = compare.run(FakeEmbedder(), runs=1)

    assert outcome["same_sections"] == outcome["questions"] == len(QUESTIONS)
    assert outcome["direct"]["size_kb"] > 0
    assert outcome["llama_index"]["size_kb"] > 0


def test_report_shows_both_columns():
    side = {
        "search": {"searches_per_run": 100, "p50_ms": [5.0, 5.3], "p95_ms": [6.2, 8.4]},
        "open_ms": [100.0, 120.0],
        "build_ms": [800.0, 900.0],
        "size_kb": 540,
    }
    outcome = {
        "questions": 20,
        "sections": 28,
        "runs": 3,
        "top": 5,
        "same_sections": 20,
        "max_score_gap": 0.0001,
        "direct": side,
        "llama_index": {**side, "size_kb": 596},
    }

    text = compare.markdown(outcome)

    assert "| Index on disk (KB) | 540 | 596 |" in text
    assert "| Search p50 (ms) | 5.0–5.3 | 5.0–5.3 |" in text
    assert "20 of 20 questions" in text
    assert "3 runs of 100 searches each" in text
