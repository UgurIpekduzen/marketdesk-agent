"""Tests for the policy index built and searched through LlamaIndex.

The embedding model is replaced by the stand-in from conftest.py. The
second index must store the same text and give the same results as the
direct one; only the layer in between differs.
"""

import numpy as np
import pytest
from llama_index.core.schema import MetadataMode

from src.knowledge import llamaindex_policy_index
from src.knowledge.llamaindex_policy_index import (
    E5Embedding,
    LlamaIndexPolicyIndex,
    build_index,
    section_node,
)
from src.knowledge.policy_index import read_sections, source_hash
from tests.test_policy_index import folder_hash

QUESTIONS = [
    "iade süresi kaç gün",
    "kargom gecikti ne yapmalıyım",
    "siparişimi iptal edebilir miyim",
    "ürün hasarlı geldi",
    "para iadesi ne zaman yatar",
]


@pytest.fixture(scope="module")
def llamaindex_index(fake_embedder, tmp_path_factory):
    index_dir = tmp_path_factory.mktemp("policy-index-llamaindex") / "index"
    build_index(fake_embedder, index_dir)
    return LlamaIndexPolicyIndex(fake_embedder, index_dir)


def test_a_node_embeds_the_same_text_as_the_direct_index():
    for section in read_sections():
        node = section_node(section)

        assert node.get_content(MetadataMode.EMBED) == section.embedding_text
        assert node.get_content() == section.text


def test_the_wrapped_embedder_keeps_queries_and_passages_apart():
    class Recorder:
        def embed_queries(self, texts):
            return np.array([[1.0, 0.0] for _ in texts])

        def embed_passages(self, texts):
            return np.array([[0.0, 1.0] for _ in texts])

    model = E5Embedding(Recorder())

    assert model.get_query_embedding("soru") == [1.0, 0.0]
    assert model.get_text_embedding("metin") == [0.0, 1.0]
    assert model.get_text_embedding_batch(["a", "b"]) == [[0.0, 1.0], [0.0, 1.0]]


def test_every_section_is_stored_with_the_source_hash(llamaindex_index):
    assert len(llamaindex_index) == 28
    assert llamaindex_index.source_hash == source_hash(read_sections())


@pytest.mark.parametrize("question", QUESTIONS)
def test_both_indexes_give_the_same_results(
    llamaindex_index, fake_policy_index, question
):
    direct = fake_policy_index.search(question, 5)
    through_llamaindex = llamaindex_index.search(question, 5)

    assert [result["citation"] for result in through_llamaindex] == [
        result["citation"] for result in direct
    ]
    for ours, theirs in zip(through_llamaindex, direct, strict=True):
        assert ours["score"] == pytest.approx(theirs["score"], abs=1e-4)
        assert {**ours, "score": None} == {**theirs, "score": None}


def test_asking_for_more_sections_than_exist_returns_them_all(llamaindex_index):
    assert len(llamaindex_index.search("iade", 50)) == 28


def test_searching_leaves_the_stored_index_untouched(fake_embedder, tmp_path):
    index_dir = tmp_path / "index"
    build_index(fake_embedder, index_dir)
    before = folder_hash(index_dir)

    LlamaIndexPolicyIndex(fake_embedder, index_dir).search("iade süresi", 5)

    assert folder_hash(index_dir) == before


def test_rebuilding_replaces_the_old_index(fake_embedder, tmp_path):
    policies = tmp_path / "policies"
    policies.mkdir()
    (policies / "one.md").write_text(
        "# Bir\n\n## 1. İlk\n\nMetin.\n\nKural: R1\n", encoding="utf-8"
    )
    index_dir = tmp_path / "index"

    assert build_index(fake_embedder, index_dir, policies) == 1
    (policies / "one.md").write_text(
        "# Bir\n\n## 1. İlk\n\nMetin.\n\n## 2. İkinci\n\nBaşka metin.\n",
        encoding="utf-8",
    )
    assert build_index(fake_embedder, index_dir, policies) == 2
    assert len(LlamaIndexPolicyIndex(fake_embedder, index_dir)) == 2


def test_the_index_has_its_own_folder():
    from src.knowledge.policy_index import INDEX_DIR

    assert llamaindex_policy_index.INDEX_DIR != INDEX_DIR
    assert llamaindex_policy_index.INDEX_DIR.parent == INDEX_DIR.parent


# --- The index stored in the repository ---------------------------------


def test_stored_index_is_not_stale(fake_embedder):
    # Fails when a policy or the model settings changed without a rebuild:
    # run `task index:build`.
    stored = LlamaIndexPolicyIndex(fake_embedder)

    assert stored.source_hash == source_hash(read_sections())
    assert len(stored) == 28


def test_stored_index_is_not_changed_by_being_opened(fake_embedder):
    before = folder_hash(llamaindex_policy_index.INDEX_DIR)

    LlamaIndexPolicyIndex(fake_embedder)

    assert folder_hash(llamaindex_policy_index.INDEX_DIR) == before


def test_stored_index_holds_the_same_vectors_as_the_direct_one(fake_embedder):
    from src.knowledge.policy_index import PolicyIndex

    def vectors(index):
        stored = index._collection.get(include=["embeddings"])
        return dict(zip(stored["ids"], stored["embeddings"], strict=True))

    ours = vectors(LlamaIndexPolicyIndex(fake_embedder))
    theirs = vectors(PolicyIndex(fake_embedder))

    assert ours.keys() == theirs.keys()
    for section_id, vector in ours.items():
        assert vector == pytest.approx(theirs[section_id], abs=1e-6)
