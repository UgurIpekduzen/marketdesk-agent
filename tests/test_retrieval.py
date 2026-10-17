"""Retrieval quality with the real embedding model and the stored index.

These tests download the model on first use, so they are marked "model"
and left out of the default run. Run them with `task test:model`.

Measured: 14 of 20 questions find the expected section first, 18 in the
top three, 18 in the top five (the same on the code of 2026-10-08 and after
the move to LlamaIndex). The floors are 14, 16 and 17: a change to the
policies, to the chunking or to the model that makes search worse shows up
here.
"""

import pytest

from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import PolicyIndex, read_sections
from src.tools.policies import search_policies
from tests.retrieval_questions import QUESTIONS

pytestmark = pytest.mark.model

FILE_OF_DOCUMENT = {section.document: section.file for section in read_sections()}


@pytest.fixture(scope="module")
def index():
    return PolicyIndex(load_embedder())


@pytest.fixture(scope="module")
def ranks(index):
    """For every question, the rank of the best expected section (1 = first)."""
    found = []
    for _, question, expected in QUESTIONS:
        results = index.search(question, 28)
        positions = [
            position
            for position, result in enumerate(results, start=1)
            if (FILE_OF_DOCUMENT[result["document"]], result["section"]) in expected
        ]
        found.append(min(positions))
    return found


def test_damaged_item_query_finds_the_damaged_item_policy_in_the_top_three(index):
    results = search_policies(index, "hasarlı ürün", 3)["results"]

    assert "Hasarlı veya Yanlış Ürün Politikası" in [r["document"] for r in results]


def test_every_rule_has_a_question_and_every_rule_is_found(ranks):
    best_rank_per_rule = {}
    for (rule, _, _), rank in zip(QUESTIONS, ranks, strict=True):
        if rule is not None:
            best_rank_per_rule[rule] = min(rank, best_rank_per_rule.get(rule, rank))

    assert set(best_rank_per_rule) == {f"R{number}" for number in range(14)}
    assert all(rank <= 5 for rank in best_rank_per_rule.values()), best_rank_per_rule


def test_retrieval_stays_at_the_measured_level(ranks):
    first = sum(rank == 1 for rank in ranks)
    top_three = sum(rank <= 3 for rank in ranks)
    top_five = sum(rank <= 5 for rank in ranks)

    assert (first, top_three, top_five) >= (14, 16, 17), ranks
    assert top_three >= 16
    assert top_five >= 17


def test_uncovered_question_finds_the_section_that_says_so(index):
    results = search_policies(index, "İade kargosunun ücretini kim öder?", 5)["results"]

    assert "İade Politikası, Bölüm 7" in [result["citation"] for result in results]


def test_scores_are_cosine_similarities(index):
    results = index.search("iade süresi kaç gün", 5)

    assert all(0 < result["score"] <= 1 for result in results)
