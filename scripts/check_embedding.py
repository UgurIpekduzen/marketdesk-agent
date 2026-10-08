"""Load the real embedding model and show that it works.

Usage:  python scripts/check_embedding.py

Downloads the model on first use, so it needs the network once. It is not
part of the unit tests for that reason. It embeds the sections of the policy
documents and prints the three closest to a few questions, with the memory
the process uses.
"""

import re
import resource
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Run as a plain script, Python only searches the scripts/ folder for imports.
sys.path.insert(0, str(PROJECT_ROOT))

import config
from src.knowledge.embedding import load_embedder

QUESTIONS = (
    "hasarlı ürün",
    "Siparişimi iptal etmek istiyorum",
    "Kargo çok geç geldi, kargo ücretini geri alabilir miyim?",
    "Hediye çekiyle ödedim, iadem nasıl yapılır?",
)


def peak_memory_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def policy_sections() -> list[tuple[str, str]]:
    """(document title + section heading, section text) for every section."""
    sections = []
    for path in sorted((PROJECT_ROOT / "policies").glob("*.md")):
        title, *parts = re.split(
            r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE
        )
        document = title.splitlines()[0].removeprefix("# ")
        for part in parts:
            heading, _, body = part.partition("\n")
            sections.append((f"{document}, Bölüm {heading}", body.strip()))
    return sections


def main() -> int:
    started = time.perf_counter()
    embedder = load_embedder()
    print(f"Model: {config.EMBEDDING_MODEL_REPO} / {config.EMBEDDING_MODEL_FILE}")
    print(f"Loaded in {time.perf_counter() - started:.1f} s")

    sections = policy_sections()
    passages = embedder.embed_passages([text for _, text in sections])
    print(f"{len(sections)} policy sections, {passages.shape[1]} dimensions")
    if passages.shape[1] != config.EMBEDDING_DIMENSIONS:
        print("Unexpected number of dimensions.")
        return 1

    queries = embedder.embed_queries(list(QUESTIONS))
    for question, query in zip(QUESTIONS, queries, strict=True):
        scores = passages @ query
        print(f"\n{question}")
        for index in scores.argsort()[::-1][:3]:
            print(f"  {scores[index]:.3f}  {sections[index][0]}")

    print(f"\nPeak memory of this process: {peak_memory_mb():.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
