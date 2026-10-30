"""Does the policy search through LlamaIndex give what direct Chroma gives?

Usage:  python eval/index_compare.py [--runs N]

The policy search first used Chroma directly. It now goes through LlamaIndex
(`VectorStoreIndex` over `ChromaVectorStore`, src/knowledge/policy_index.py).
This builds both over the same sections, with the same embedding model and the
same vectors, asks both the retrieval questions of tests/test_retrieval.py,
and compares what comes back and what it costs.

The direct version here is the one the project had before the move: a Chroma
collection with cosine distance, filled with the section vectors, queried with
the query vector. Nothing here is imported by the application.

Measured: whether the top five sections and their scores are the same, the
time of a search (the query embedding included, as in the product), of opening
and of building an index, and the size on disk. Memory is not measured here:
it depends on what else the process has loaded.
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.terminal_table import terminal_tables
from src.knowledge.embedding import Embedder, load_embedder
from src.knowledge.policy_index import (
    COLLECTION,
    PolicyIndex,
    build_index,
    chroma_client,
    read_sections,
    search_result,
    section_metadata,
    source_hash,
)
from tests.retrieval_questions import QUESTIONS

RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
TOP = 5
# Every question is asked this many times in a run of searches.
REPEATS = 5


# --- The direct version -----------------------------------------------------------


def build_direct(embedder: Embedder, sections: list, folder: Path) -> None:
    """The index as it was built before LlamaIndex: one batch, cosine distance."""
    collection = chroma_client(folder).create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine", "source_hash": source_hash(sections)},
        embedding_function=None,
    )
    collection.add(
        ids=[section.id for section in sections],
        embeddings=embedder.embed_passages(
            [section.embedding_text for section in sections]
        ).tolist(),
        documents=[section.text for section in sections],
        metadatas=[section_metadata(section) for section in sections],
    )


class DirectIndex:
    """A stored index opened for searching, straight through chromadb."""

    def __init__(self, embedder: Embedder, index_dir: Path) -> None:
        # Chroma writes to its files even when it only reads: open a copy.
        self._copy = Path(tempfile.mkdtemp(prefix="direct-index-")) / "index"
        shutil.copytree(index_dir, self._copy)
        self._collection = chroma_client(self._copy).get_collection(
            COLLECTION, embedding_function=None
        )
        self._embedder = embedder

    def search(self, query: str, k: int) -> list[dict]:
        found = self._collection.query(
            query_embeddings=self._embedder.embed_queries([query]).tolist(),
            n_results=min(k, self._collection.count()),
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


# --- Comparing --------------------------------------------------------------------


def section_ids(results: list[dict]) -> list[tuple[str, int]]:
    return [(result["document"], result["section"]) for result in results]


def compare_answers(direct: list[dict], llama: list[dict]) -> dict:
    """Same sections in the same order, and how far apart the scores are."""
    same = section_ids(direct) == section_ids(llama)
    gap = max(
        (abs(a["score"] - b["score"]) for a, b in zip(direct, llama, strict=False)),
        default=0.0,
    )
    return {"same_sections": same, "max_score_gap": round(gap, 4)}


def milliseconds(action, times: int = 1) -> float:
    start = time.perf_counter()
    for _ in range(times):
        action()
    return (time.perf_counter() - start) * 1000 / times


def search_times(index, questions: list[str]) -> list[float]:
    return [
        milliseconds(lambda q=question: index.search(q, TOP)) for question in questions
    ]


def percentile(values: list[float], share: float) -> float:
    return float(np.percentile(values, share))


def folder_size_kb(folder: Path) -> int:
    return round(
        sum(path.stat().st_size for path in folder.rglob("*") if path.is_file()) / 1024
    )


def run(embedder: Embedder, runs: int) -> dict:
    sections = read_sections()
    questions = [question for _, question, _ in QUESTIONS]
    work = Path(tempfile.mkdtemp(prefix="index-compare-"))
    build_ms = {"direct": [], "llama": []}
    for number in range(runs):
        # Chroma remembers the folders it has opened in this process: every
        # build gets a folder of its own, as in the product's build.
        direct_dir = work / f"direct-{number}"
        llama_dir = work / f"llama-{number}"
        build_ms["direct"].append(
            milliseconds(lambda path=direct_dir: build_direct(embedder, sections, path))
        )
        build_ms["llama"].append(
            milliseconds(lambda path=llama_dir: build_index(embedder, path))
        )

    open_ms = {"direct": [], "llama": []}
    for _ in range(runs):
        open_ms["direct"].append(
            milliseconds(lambda: DirectIndex(embedder, direct_dir))
        )
        open_ms["llama"].append(milliseconds(lambda: PolicyIndex(embedder, llama_dir)))

    direct, llama = DirectIndex(embedder, direct_dir), PolicyIndex(embedder, llama_dir)
    answers = [
        compare_answers(direct.search(question, TOP), llama.search(question, TOP))
        for question in questions
    ]

    # One pass first, so that neither side pays for the first call.
    search_times(direct, questions)
    search_times(llama, questions)
    times = {"direct": [], "llama": []}
    for _ in range(runs):
        # The two take turns inside a run, so that a slow moment hits both.
        direct_run, llama_run = [], []
        for _ in range(REPEATS):
            direct_run += search_times(direct, questions)
            llama_run += search_times(llama, questions)
        times["direct"].append(direct_run)
        times["llama"].append(llama_run)

    def search_summary(kind: str) -> dict:
        per_run = times[kind]
        p50 = [percentile(run_times, 50) for run_times in per_run]
        p95 = [percentile(run_times, 95) for run_times in per_run]
        return {
            "searches_per_run": len(per_run[0]),
            "p50_ms": [round(min(p50), 1), round(max(p50), 1)],
            "p95_ms": [round(min(p95), 1), round(max(p95), 1)],
        }

    def range_of(values: list[float]) -> list[float]:
        return [round(min(values), 1), round(max(values), 1)]

    result = {
        "questions": len(questions),
        "sections": len(sections),
        "runs": runs,
        "top": TOP,
        "same_sections": sum(answer["same_sections"] for answer in answers),
        "max_score_gap": max(answer["max_score_gap"] for answer in answers),
        "per_question": answers,
        "direct": {
            "search": search_summary("direct"),
            "open_ms": range_of(open_ms["direct"]),
            "build_ms": range_of(build_ms["direct"]),
            "size_kb": folder_size_kb(direct_dir),
        },
        "llama_index": {
            "search": search_summary("llama"),
            "open_ms": range_of(open_ms["llama"]),
            "build_ms": range_of(build_ms["llama"]),
            "size_kb": folder_size_kb(llama_dir),
        },
    }
    shutil.rmtree(work, ignore_errors=True)
    return result


# --- Report -----------------------------------------------------------------------


def span(values: list[float]) -> str:
    low, high = values
    return f"{low}" if low == high else f"{low}–{high}"


def row(label: str, direct, llama) -> str:
    return f"| {label} | {direct} | {llama} |"


def markdown(result: dict) -> str:
    direct, llama = result["direct"], result["llama_index"]
    searches = direct["search"]["searches_per_run"]
    same = f"{result['same_sections']} of {result['questions']} questions"
    return "\n".join(
        [
            "# Policy search: direct Chroma and LlamaIndex",
            "",
            (
                f"{result['questions']} questions, {result['sections']} policy "
                f"sections, multilingual-e5-small, {result['runs']} runs of "
                f"{searches} searches each. Times are the lowest and highest of the "
                "runs; a search includes embedding the query."
            ),
            "",
            "| | Direct Chroma | LlamaIndex |",
            "|---|---|---|",
            row(
                f"Same top {result['top']} in the same order as direct",
                "(reference)",
                same,
            ),
            row(
                "Largest gap between two scores", "(reference)", result["max_score_gap"]
            ),
            row(
                "Search p50 (ms)",
                span(direct["search"]["p50_ms"]),
                span(llama["search"]["p50_ms"]),
            ),
            row(
                "Search p95 (ms)",
                span(direct["search"]["p95_ms"]),
                span(llama["search"]["p95_ms"]),
            ),
            row(
                "Opening the index (ms)",
                span(direct["open_ms"]),
                span(llama["open_ms"]),
            ),
            row(
                "Building the index (ms)",
                span(direct["build_ms"]),
                span(llama["build_ms"]),
            ),
            row("Index on disk (KB)", direct["size_kb"], llama["size_kb"]),
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=3, help="runs of the timings")
    args = parser.parse_args()

    result = run(load_embedder(), args.runs)
    print(f"\n{terminal_tables(markdown(result))}")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "index_compare_v1.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (RESULTS_DIR / "index_compare_v1.md").write_text(markdown(result), encoding="utf-8")
    print("Results written to eval/results/index_compare_v1.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
