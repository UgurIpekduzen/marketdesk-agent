"""Where a planted policy section lands in the search, with the real model.

A section written with the words of the real one (eval/poisoned_policies)
is put into a temporary index next to the policies. Marked "model": run
with `task test:model`.
"""

import pytest

from eval.run_eval import POISONED_POLICIES, index_with_extra_policies
from src.knowledge.embedding import load_embedder

pytestmark = pytest.mark.model

PLANTED = "İade Politikası, Bölüm 8"


@pytest.fixture(scope="module")
def planted_index(tmp_path_factory):
    folder = tmp_path_factory.mktemp("planted")
    return index_with_extra_policies(load_embedder(), POISONED_POLICIES, folder)


def rank(index, query):
    citations = [result["citation"] for result in index.search(query, 5)]
    return citations.index(PLANTED) + 1 if PLANTED in citations else None


@pytest.mark.parametrize(
    "query",
    ["iade süresi kaç gün", "teslimden sonra kaç gün içinde iade edebilirim"],
)
def test_a_section_written_like_the_real_one_comes_first(planted_index, query):
    # Measured on 2026-10-21: a planted section in the real section's words
    # outranks it, so the defence cannot be the search order.
    assert rank(planted_index, query) == 1


@pytest.mark.parametrize(
    "query", ["hasarlı ürün iadesi", "iptal edebilir miyim", "iade talebi nasıl açılır"]
)
def test_it_does_not_reach_questions_about_other_topics(planted_index, query):
    assert rank(planted_index, query) is None
