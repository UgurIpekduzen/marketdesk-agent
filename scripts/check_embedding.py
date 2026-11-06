"""Load the real embedding model and show that it works.

Usage:  python -m scripts.check_embedding

Downloads the model on first use, so it needs the network once. It is not
part of the unit tests for that reason. It embeds the sections of the policy
documents and prints the three closest to a few questions, with the memory
the process uses.
"""

import resource
import sys
import time

import config
from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import read_sections

QUESTIONS = (
    "hasarlı ürün",
    "Siparişimi iptal etmek istiyorum",
    "Kargo çok geç geldi, kargo ücretini geri alabilir miyim?",
    "Hediye çekiyle ödedim, iadem nasıl yapılır?",
)


def peak_memory_mb() -> float:
    """Peak memory of this process, in MB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    """Run the command line entry point."""
    started = time.perf_counter()
    embedder = load_embedder()
    print(f"Model: {config.EMBEDDING_MODEL_REPO} / {config.EMBEDDING_MODEL_FILE}")
    print(f"Loaded in {time.perf_counter() - started:.1f} s")

    sections = read_sections()
    passages = embedder.embed_passages([section.embedding_text for section in sections])
    print(f"{len(sections)} policy sections, {passages.shape[1]} dimensions")
    if passages.shape[1] != config.EMBEDDING_DIMENSIONS:
        print("Unexpected number of dimensions.")
        return 1

    queries = embedder.embed_queries(list(QUESTIONS))
    for question, query in zip(QUESTIONS, queries, strict=True):
        scores = passages @ query
        print(f"\n{question}")
        for index in scores.argsort()[::-1][:3]:
            print(f"  {scores[index]:.3f}  {sections[index].citation}")

    print(f"\nPeak memory of this process: {peak_memory_mb():.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
