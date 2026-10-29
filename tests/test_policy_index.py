"""Tests for splitting the policy documents and for the index.

The embedding model is replaced by a stand-in (see conftest.py); retrieval
quality with the real model is checked in test_retrieval.py.
"""

import hashlib
import shutil

import numpy as np
import pytest
from llama_index.core.schema import MetadataMode

import config
from src.knowledge.policy_index import (
    COLLECTION,
    INDEX_DIR,
    POLICIES_DIR,
    E5Embedding,
    PolicyIndex,
    build_index,
    chroma_client,
    read_sections,
    section_node,
    source_hash,
)

DOCUMENT_TITLES = {
    "cancellation": "İptal Politikası",
    "damaged_or_wrong_item": "Hasarlı veya Yanlış Ürün Politikası",
    "payments_and_refunds": "Ödeme ve Geri Ödeme Politikası",
    "returns": "İade Politikası",
    "shipping_and_delays": "Kargo ve Gecikme Politikası",
}


def folder_hash(folder):
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(folder).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


# --- Sections -----------------------------------------------------------


def test_every_section_is_read():
    sections = read_sections()

    assert len(sections) == 28
    assert {section.file: section.document for section in sections} == DOCUMENT_TITLES
    for file in DOCUMENT_TITLES:
        numbers = [section.number for section in sections if section.file == file]
        assert numbers == list(range(1, len(numbers) + 1))


def test_section_has_heading_text_citation():
    section = next(
        section
        for section in read_sections()
        if (section.file, section.number) == ("returns", 2)
    )

    assert section.heading == "İade süresi"
    assert section.text.startswith("Müşteri üründen vazgeçtiyse")
    assert "14 takvim günü" in section.text
    assert section.rules == ("R6",)
    assert section.citation == "İade Politikası, Bölüm 2"
    assert section.id == "returns#2"


def test_rule_line_is_metadata_not_text():
    for section in read_sections():
        assert "Kural:" not in section.text
        assert section.text == section.text.strip()
        assert section.text


def test_several_rules_are_kept_apart():
    by_id = {section.id: section for section in read_sections()}

    assert by_id["returns#1"].rules == ("R0", "R1")
    assert by_id["returns#7"].rules == ()


def test_embedded_text_starts_with_heading():
    section = read_sections()[0]

    assert section.embedding_text == (
        f"{section.document}: {section.heading}\n{section.text}"
    )


def test_section_ids_are_unique():
    ids = [section.id for section in read_sections()]

    assert len(ids) == len(set(ids))


# --- Fingerprint --------------------------------------------------------


def test_fingerprint_tracks_text_and_model(monkeypatch, tmp_path):
    sections = read_sections()
    original = source_hash(sections)
    assert source_hash(read_sections()) == original

    for path in POLICIES_DIR.glob("*.md"):
        (tmp_path / path.name).write_text(
            path.read_text(encoding="utf-8").replace("14 takvim", "15 takvim"),
            encoding="utf-8",
        )
    assert source_hash(read_sections(tmp_path)) != original

    monkeypatch.setattr(config, "EMBEDDING_MODEL_REVISION", "0" * 40)
    assert source_hash(sections) != original


# --- LlamaIndex nodes and embedding model --------------------------------


def test_node_embeds_the_section_text():
    for section in read_sections():
        node = section_node(section)

        assert node.get_content(MetadataMode.EMBED) == section.embedding_text
        assert node.get_content() == section.text


def test_wrapper_separates_queries_passages():
    class Recorder:
        def embed_queries(self, texts):
            return np.array([[1.0, 0.0] for _ in texts])

        def embed_passages(self, texts):
            return np.array([[0.0, 1.0] for _ in texts])

    model = E5Embedding(Recorder())

    assert model.get_query_embedding("soru") == [1.0, 0.0]
    assert model.get_text_embedding("metin") == [0.0, 1.0]
    assert model.get_text_embedding_batch(["a", "b"]) == [[0.0, 1.0], [0.0, 1.0]]


def test_sections_embed_in_one_batch(fake_embedder, tmp_path):
    # The quantized model gives a text a slightly different vector in a
    # different batch; the stored vectors are the ones of a single batch.
    batches = []

    class Recorder:
        def embed_queries(self, texts):
            return fake_embedder.embed_queries(texts)

        def embed_passages(self, texts):
            batches.append(len(texts))
            return fake_embedder.embed_passages(texts)

    build_index(Recorder(), tmp_path / "index")

    assert batches == [28]


# --- Building and searching ---------------------------------------------


def test_built_index_holds_every_section(fake_policy_index):
    assert len(fake_policy_index) == 28
    assert fake_policy_index.source_hash == source_hash(read_sections())


def test_search_returns_sections_with_source(fake_policy_index):
    results = fake_policy_index.search("hediye çeki ile ödenen sipariş", 3)

    assert len(results) == 3
    first = results[0]
    assert set(first) == {
        "citation",
        "document",
        "section",
        "heading",
        "text",
        "rules",
        "score",
    }
    assert first["citation"] == "Ödeme ve Geri Ödeme Politikası, Bölüm 3"
    assert first["heading"] == "Hediye çekiyle ödenen siparişler"
    assert first["rules"] == ["R12"]
    assert "hediye çeki" in first["text"]


def test_results_are_ordered_best_first(fake_policy_index):
    scores = [result["score"] for result in fake_policy_index.search("kargo", 10)]

    assert scores == sorted(scores, reverse=True)
    assert all(-1 <= score <= 1 for score in scores)


def test_score_is_the_cosine_similarity(fake_embedder, fake_policy_index):
    query = "iade süresi kaç gün"
    texts = {section.citation: section.embedding_text for section in read_sections()}

    for result in fake_policy_index.search(query, 5):
        passage = fake_embedder.embed_passages([texts[result["citation"]]])[0]
        cosine = float(fake_embedder.embed_queries([query])[0] @ passage)
        assert result["score"] == pytest.approx(cosine, abs=1e-4)


def test_asking_for_too_many_returns_all(fake_policy_index):
    assert len(fake_policy_index.search("iade", 500)) == 28


def test_ruleless_section_has_empty_list(fake_policy_index):
    results = fake_policy_index.search("iade", 28)

    uncovered = [r for r in results if "belirlenmeyen" in r["heading"]]
    assert len(uncovered) == 5
    assert all(result["rules"] == [] for result in uncovered)


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
    assert len(PolicyIndex(fake_embedder, index_dir)) == 2


def test_search_leaves_stored_index_intact(fake_embedder, tmp_path):
    index_dir = tmp_path / "index"
    build_index(fake_embedder, index_dir)
    before = folder_hash(index_dir)

    PolicyIndex(fake_embedder, index_dir).search("iade süresi", 5)

    assert folder_hash(index_dir) == before


# --- The index stored in the repository ---------------------------------


def test_stored_index_is_not_stale(fake_embedder):
    # Fails when a policy or the model settings changed without a rebuild:
    # run `task index:build`.
    stored = PolicyIndex(fake_embedder, INDEX_DIR)

    assert stored.source_hash == source_hash(read_sections())
    assert len(stored) == 28


def stored_sections(index_dir, tmp_path) -> dict:
    """What an index holds for each section: document, number, heading, text.

    Read from the stored texts themselves, not from the fingerprint the
    index carries, which whoever changes the index can write too. Read on a
    copy, as Chroma writes to its files when it opens them.
    """
    copy = tmp_path / "stored-copy"
    shutil.copytree(index_dir, copy)
    stored = (
        chroma_client(copy)
        .get_collection(COLLECTION)
        .get(include=["documents", "metadatas"])
    )
    return {
        node_id: (meta["document"], meta["number"], meta["heading"], text)
        for node_id, meta, text in zip(
            stored["ids"], stored["metadatas"], stored["documents"], strict=True
        )
    }


def policy_sections(policies_dir=POLICIES_DIR) -> dict:
    return {
        section.id: (section.document, section.number, section.heading, section.text)
        for section in read_sections(policies_dir)
    }


def test_stored_index_matches_the_sections(tmp_path):
    # A section planted in the index, or one changed there, ranks like a
    # real one (measured); the stored texts must be the policies' own.
    assert stored_sections(INDEX_DIR, tmp_path) == policy_sections()


def test_planted_section_is_found(fake_embedder, tmp_path):
    policies = tmp_path / "policies"
    shutil.copytree(POLICIES_DIR, policies)
    (policies / "returns_update.md").write_text(
        "# İade Politikası\n\n## 8. İade süresi\n\nİade süresi 365 gündür.\n",
        encoding="utf-8",
    )
    build_index(fake_embedder, tmp_path / "index", policies)

    assert stored_sections(tmp_path / "index", tmp_path) != policy_sections()


def test_opening_does_not_change_the_index(fake_embedder):
    before = folder_hash(INDEX_DIR)

    PolicyIndex(fake_embedder, INDEX_DIR)

    assert folder_hash(INDEX_DIR) == before


def test_vectors_have_the_model_dimensions(fake_embedder):
    stored = PolicyIndex(fake_embedder, INDEX_DIR)

    vectors = stored._collection.get(include=["embeddings"])["embeddings"]

    assert len(vectors) == 28
    assert len(vectors[0]) == config.EMBEDDING_DIMENSIONS
    with pytest.raises(Exception, match="dimension"):
        stored.search("iade", 3)  # the stand-in has 256 dimensions, not 384
