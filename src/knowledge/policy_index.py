"""The policy documents as a searchable index, built and searched through
LlamaIndex.

Each numbered section of a policy document is one chunk: a section covers
one topic, is short, and is exactly what an answer cites ("document,
section"). Nothing is cut in the middle and nothing overlaps.

The text that is embedded is "document title: section heading" followed by
the section text. The "Kural: ..." line is taken out of the text and kept
as metadata: it names rule ids, which do not help a search.

- The ONNX embedder is wrapped as a LlamaIndex embedding model; queries and
  passages keep their "query: " and "passage: " prefixes.
- Each section is a TextNode whose text for embedding is built by the
  node's own templates.
- The vectors go to a Chroma collection through ChromaVectorStore, and a
  search is a VectorStoreIndex retriever over it.

The index is built locally with `task index:build` and stored in
policies/index/, so the deployed application does not embed the documents
again. A hash of the sections and of the model settings is stored with it;
when it no longer matches, the index is stale and must be rebuilt.
"""

import hashlib
import json
import math
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import chromadb
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import TextNode
from llama_index.vector_stores.chroma import ChromaVectorStore
from pydantic import PrivateAttr

import config
from src import messages
from src.knowledge.embedding import Embedder

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POLICIES_DIR = PROJECT_ROOT / "policies"
INDEX_DIR = POLICIES_DIR / "index"
COLLECTION = "policies"

SECTION_START = re.compile(r"^## ", re.MULTILINE)
RULE_LINE = re.compile(r"^Kural: (.+)$", re.MULTILINE)
# Only the document title and the heading go in front of the text, as
# "document: heading", the same as Section.embedding_text.
NOT_EMBEDDED = ["file", "number", "rules"]


@dataclass(frozen=True)
class Section:
    """One numbered section of a policy document."""

    file: str  # file name without .md, for example "returns"
    document: str  # the document's title
    number: int
    heading: str
    text: str  # the section text without its "Kural:" line
    rules: tuple[str, ...]

    @property
    def id(self) -> str:
        """Stable id of the section: file name and number."""
        return f"{self.file}#{self.number}"

    @property
    def citation(self) -> str:
        """The citation shown to the person: document title and section number."""
        return messages.POLICY_CITATION.format(
            document=self.document, number=self.number
        )

    @property
    def embedding_text(self) -> str:
        """The text that is embedded: title, heading and body."""
        return f"{self.document}: {self.heading}\n{self.text}"


def read_sections(policies_dir: Path = POLICIES_DIR) -> list[Section]:
    """Split every policy document into its numbered sections.

    Args:
        policies_dir (Path): The folder with the policy documents.

    Returns:
        Every numbered section of every document.
    """
    sections = []
    for path in sorted(policies_dir.glob("*.md")):
        introduction, *parts = SECTION_START.split(path.read_text(encoding="utf-8"))
        document = introduction.splitlines()[0].removeprefix("# ").strip()
        for part in parts:
            title, _, body = part.partition("\n")
            number, _, heading = title.partition(". ")
            rule_line = RULE_LINE.search(body)
            sections.append(
                Section(
                    file=path.stem,
                    document=document,
                    number=int(number),
                    heading=heading.strip(),
                    text=RULE_LINE.sub("", body).strip(),
                    rules=tuple(rule_line.group(1).split(", ")) if rule_line else (),
                )
            )
    return sections


def source_hash(sections: list[Section]) -> str:
    """A fingerprint of everything the stored vectors depend on.

    Args:
        sections (list[Section]): The policy sections.

    Returns:
        A hash of the sections and the embedding model.
    """
    content = {
        "sections": [asdict(section) for section in sections],
        "model": [
            config.EMBEDDING_MODEL_REPO,
            config.EMBEDDING_MODEL_REVISION,
            config.EMBEDDING_MODEL_FILE,
        ],
    }
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def section_metadata(section: Section) -> dict:
    """What is stored next to a section's vector (Chroma takes flat values).

    Args:
        section (Section): A policy section.

    Returns:
        The values stored next to its vector.
    """
    return {
        "file": section.file,
        "document": section.document,
        "number": section.number,
        "heading": section.heading,
        "rules": ", ".join(section.rules),
    }


def search_result(text: str, metadata: dict, distance: float) -> dict:
    """One search result, as the policy tool returns it.

    Args:
        text (str): The section text.
        metadata (dict): The metadata stored with the section.
        distance (float): The cosine distance of the section from the query.

    Returns:
        The result in the shape the policy tool returns.
    """
    return {
        "citation": messages.POLICY_CITATION.format(
            document=metadata["document"], number=metadata["number"]
        ),
        "document": metadata["document"],
        "section": metadata["number"],
        "heading": metadata["heading"],
        "text": text,
        "rules": metadata["rules"].split(", ") if metadata["rules"] else [],
        # Cosine similarity: 1 is the same direction.
        "score": round(1 - distance, 4),
    }


def chroma_client(path: Path) -> chromadb.ClientAPI:
    """Open a persistent Chroma client at the path, with telemetry off.

    Args:
        path (Path): The folder of the index.

    Returns:
        The Chroma client.
    """
    return chromadb.PersistentClient(
        path=str(path), settings=chromadb.Settings(anonymized_telemetry=False)
    )


class E5Embedding(BaseEmbedding):
    """The project's ONNX embedder as a LlamaIndex embedding model."""

    _embedder: Any = PrivateAttr()

    def __init__(self, embedder: Embedder, batch_size: int = 10) -> None:
        super().__init__(
            model_name="multilingual-e5-small", embed_batch_size=batch_size
        )
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
    """Make the LlamaIndex node that stores one section.

    Args:
        section (Section): A policy section.

    Returns:
        The node that stores it.
    """
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
    """Embed every section and write the index from scratch.

    Args:
        embedder (Embedder): The model that embeds the sections.
        index_dir (Path): Where the index is written.
        policies_dir (Path): The folder with the policy documents.

    Returns:
        The number of sections written.
    """
    sections = read_sections(policies_dir)
    # Built in a new folder and then moved into place: Chroma remembers the
    # folders it has opened in this process, so writing over an old index
    # where it stands would find the old collection still there.
    fresh = Path(tempfile.mkdtemp(prefix="policy-index-build-")) / "index"
    collection = chroma_client(fresh).create_collection(
        COLLECTION,
        # Cosine distance; the vectors have unit length.
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
        # (up to 0.015 apart, measured); one batch keeps the vectors the
        # agent was evaluated with.
        embed_model=E5Embedding(embedder, batch_size=len(sections)),
    )
    shutil.rmtree(index_dir, ignore_errors=True)
    shutil.copytree(fresh, index_dir)
    return len(sections)


class PolicyIndex:
    """A stored index, opened for searching."""

    def __init__(self, embedder: Embedder, index_dir: Path = INDEX_DIR) -> None:
        # Chroma writes to its files even when it only reads. Opening a copy
        # keeps the stored index unchanged and works on a read-only folder.
        self._copy = Path(tempfile.mkdtemp(prefix="policy-index-")) / "index"
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
        """Hash of the policy files the index was built from."""
        return self._collection.metadata["source_hash"]

    def __len__(self) -> int:
        return self._collection.count()

    def search(self, query: str, k: int) -> list[dict]:
        """The k sections closest to the query, best first.

        Args:
            query (str): The question.
            k (int): How many sections to return at most.

        Returns:
            The closest sections, best first.
        """
        retriever = self._index.as_retriever(similarity_top_k=min(k, len(self)))
        return [
            # ChromaVectorStore gives exp(-distance) as the score; the distance
            # is taken back, so the score is the cosine similarity.
            search_result(
                found.node.get_content(), found.node.metadata, -math.log(found.score)
            )
            for found in retriever.retrieve(query)
        ]
