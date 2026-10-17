"""The policy index built and searched through LlamaIndex.

A second way to store and search the same sections, kept next to the
direct Chroma index (policy_index.py) so the two can be compared. Only the
storing and searching layer differs: the sections, the embedding model,
the text that is embedded, the distance and the result are the same.

- The ONNX embedder is wrapped as a LlamaIndex embedding model; queries and
  passages keep their "query: " and "passage: " prefixes.
- Each section is a TextNode whose text for embedding is built by the
  node's own templates to equal Section.embedding_text.
- The vectors go to a Chroma collection through ChromaVectorStore, and a
  search is a VectorStoreIndex retriever over it.

The index is stored in policies/index_llamaindex/ and built with
`task index:build`, like the direct one.
"""

import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import TextNode
from llama_index.vector_stores.chroma import ChromaVectorStore
from pydantic import PrivateAttr

from src.knowledge.embedding import Embedder
from src.knowledge.policy_index import (
    COLLECTION,
    POLICIES_DIR,
    Section,
    chroma_client,
    read_sections,
    search_result,
    section_metadata,
    source_hash,
)

INDEX_DIR = POLICIES_DIR / "index_llamaindex"

# Only the document title and the heading go in front of the text, as
# "document: heading", the same as Section.embedding_text.
NOT_EMBEDDED = ["file", "number", "rules"]


class E5Embedding(BaseEmbedding):
    """The project's ONNX embedder as a LlamaIndex embedding model."""

    _embedder: Any = PrivateAttr()

    def __init__(self, embedder: Embedder, batch_size: int = 10) -> None:
        super().__init__(model_name="multilingual-e5-small", embed_batch_size=batch_size)
        self._embedder = embedder

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embedder.embed_queries([query])[0].tolist()

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedder.embed_passages([text])[0].tolist()

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed_passages(texts).tolist()


def section_node(section: Section) -> TextNode:
    return TextNode(
        id_=section.id,
        text=section.text,
        metadata=section_metadata(section),
        excluded_embed_metadata_keys=NOT_EMBEDDED,
        metadata_template="{value}",
        metadata_separator=": ",
        text_template="{metadata_str}\n{content}",
    )


def build_index(
    embedder: Embedder,
    index_dir: Path = INDEX_DIR,
    policies_dir: Path = POLICIES_DIR,
) -> int:
    """Embed every section through LlamaIndex and write the index from scratch."""
    sections = read_sections(policies_dir)
    # Built in a new folder and moved into place, for the same reason as the
    # direct index.
    fresh = Path(tempfile.mkdtemp(prefix="policy-index-llamaindex-build-")) / "index"
    collection = chroma_client(fresh).create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine", "source_hash": source_hash(sections)},
        embedding_function=None,
    )
    VectorStoreIndex(
        [section_node(section) for section in sections],
        storage_context=StorageContext.from_defaults(
            vector_store=ChromaVectorStore(chroma_collection=collection)
        ),
        # All sections in one batch. The quantized model gives a text a
        # slightly different vector depending on what else is in its batch
        # (up to 0.015 apart, measured); one batch keeps the vectors equal to
        # the ones the agent was evaluated with.
        embed_model=E5Embedding(embedder, batch_size=len(sections)),
    )
    shutil.rmtree(index_dir, ignore_errors=True)
    shutil.copytree(fresh, index_dir)
    return len(sections)


class LlamaIndexPolicyIndex:
    """A stored LlamaIndex index, opened for searching."""

    def __init__(self, embedder: Embedder, index_dir: Path = INDEX_DIR) -> None:
        # Opened from a copy, like the direct index: Chroma writes even when
        # it only reads.
        self._copy = Path(tempfile.mkdtemp(prefix="policy-index-llamaindex-")) / "index"
        shutil.copytree(index_dir, self._copy)
        self._collection = chroma_client(self._copy).get_collection(
            COLLECTION, embedding_function=None
        )
        self._index = VectorStoreIndex.from_vector_store(
            ChromaVectorStore(chroma_collection=self._collection),
            embed_model=E5Embedding(embedder),
        )

    @property
    def source_hash(self) -> str:
        return self._collection.metadata["source_hash"]

    def __len__(self) -> int:
        return self._collection.count()

    def search(self, query: str, k: int) -> list[dict]:
        """The k sections closest to the query, best first."""
        retriever = self._index.as_retriever(similarity_top_k=min(k, len(self)))
        return [
            # ChromaVectorStore gives exp(-distance) as the score; the distance
            # is taken back so the score is on the same scale as the direct
            # index's.
            search_result(
                found.node.get_content(), found.node.metadata, -math.log(found.score)
            )
            for found in retriever.retrieve(query)
        ]
