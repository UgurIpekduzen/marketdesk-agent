"""The policy documents as a searchable index.

Each numbered section of a policy document is one chunk: a section covers
one topic, is short, and is exactly what an answer cites ("document,
section"). Nothing is cut in the middle and nothing overlaps.

The text that is embedded is "document title: section heading" followed by
the section text. The "Kural: ..." line is taken out of the text and kept
as metadata: it names rule ids, which do not help a search.

The index is a Chroma collection built locally with `task index:build` and
stored in policies/index/, so the deployed application does not embed the
documents again. A hash of the sections and of the model settings is stored
with it; when it no longer matches, the index is stale and must be rebuilt.
"""

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import chromadb
import numpy as np

import config
from src import messages
from src.knowledge.embedding import Embedder

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
POLICIES_DIR = PROJECT_ROOT / "policies"
INDEX_DIR = POLICIES_DIR / "index"
COLLECTION = "policies"

SECTION_START = re.compile(r"^## ", re.MULTILINE)
RULE_LINE = re.compile(r"^Kural: (.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    file: str  # file name without .md, for example "returns"
    document: str  # the document's title
    number: int
    heading: str
    text: str  # the section text without its "Kural:" line
    rules: tuple[str, ...]

    @property
    def id(self) -> str:
        return f"{self.file}#{self.number}"

    @property
    def citation(self) -> str:
        return messages.POLICY_CITATION.format(
            document=self.document, number=self.number
        )

    @property
    def embedding_text(self) -> str:
        return f"{self.document}: {self.heading}\n{self.text}"


def read_sections(policies_dir: Path = POLICIES_DIR) -> list[Section]:
    """Split every policy document into its numbered sections."""
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
    """A fingerprint of everything the stored vectors depend on."""
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
    """What is stored next to a section's vector (Chroma takes flat values)."""
    return {
        "file": section.file,
        "document": section.document,
        "number": section.number,
        "heading": section.heading,
        "rules": ", ".join(section.rules),
    }


def search_result(text: str, metadata: dict, distance: float) -> dict:
    """One search result, as the policy tool returns it."""
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
    return chromadb.PersistentClient(
        path=str(path), settings=chromadb.Settings(anonymized_telemetry=False)
    )


def build_index(
    embedder: Embedder,
    index_dir: Path = INDEX_DIR,
    policies_dir: Path = POLICIES_DIR,
) -> int:
    """Embed every section and write the index from scratch."""
    sections = read_sections(policies_dir)
    vectors = embedder.embed_passages([section.embedding_text for section in sections])

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
    collection.add(
        ids=[section.id for section in sections],
        embeddings=vectors.tolist(),
        documents=[section.text for section in sections],
        metadatas=[section_metadata(section) for section in sections],
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
        self._embedder = embedder

    @property
    def source_hash(self) -> str:
        return self._collection.metadata["source_hash"]

    def __len__(self) -> int:
        return self._collection.count()

    def search(self, query: str, k: int) -> list[dict]:
        """The k sections closest to the query, best first."""
        found = self._collection.query(
            query_embeddings=np.asarray(self._embedder.embed_queries([query])).tolist(),
            n_results=min(k, len(self)),
            include=["documents", "metadatas", "distances"],
        )
        return [
            search_result(text, metadata, distance)
            for text, metadata, distance in zip(
                found["documents"][0],
                found["metadatas"][0],
                found["distances"][0],
                strict=True,
            )
        ]
