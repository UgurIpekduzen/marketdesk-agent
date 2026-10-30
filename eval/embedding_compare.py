"""Which embedding model finds the policy sections best, and what does it cost?

Usage:  python eval/embedding_compare.py              every model, results written
        python eval/embedding_compare.py --only NAME  one model, nothing written
        python eval/embedding_compare.py --list       the models

The questions are the ones tests/test_retrieval.py asks of the real index: for
each, the rank of the best expected section among all 28 (1 = first). Every
model is run on the same questions and the same section texts, with cosine
similarity. Only what the model needs differs: the prefixes E5 models expect,
and how token vectors become one text vector (mean for E5, the first token
for BGE-M3).

Each model runs in a process of its own, so that the peak memory is its own.
The quantized models give a text a slightly different vector depending on
which other texts are embedded with it, so every model is run three times:
with all the sections embedded at once (the policy index is built so), in
batches of 10, and one at a time. The results file keeps all three.

The models are downloaded once, from pinned revisions, into the Hugging Face
cache (about 970 MB for the three). The product uses multilingual-e5-small
only; nothing here is imported by the application.
"""

import argparse
import json
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.terminal_table import terminal_tables

RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
MODEL_FILE = "onnx/model_quantized.onnx"
TOKENIZER_FILE = "tokenizer.json"
MAX_TOKENS = 512
PAD_TOKEN = "<pad>"
PAD_TOKEN_ID = 1
# How the sections are embedded: all in one batch, as the policy index is
# built, in batches of 10, or one at a time.
BATCHES = ("all", "10", "1")
TOP_SHOWN = 5


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repo: str
    revision: str  # the commit that pins the exact files
    pooling: str  # "mean" or "cls"
    query_prefix: str
    passage_prefix: str


MODELS = {
    spec.name: spec
    for spec in (
        ModelSpec(
            "e5-small",
            "Xenova/multilingual-e5-small",
            "761b726dd34fb83930e26aab4e9ac3899aa1fa78",
            "mean",
            "query: ",
            "passage: ",
        ),
        ModelSpec(
            "e5-base",
            "Xenova/multilingual-e5-base",
            "1ec9243030a27d1a115d5c340572074c125b58b2",
            "mean",
            "query: ",
            "passage: ",
        ),
        ModelSpec(
            "bge-m3",
            "Xenova/bge-m3",
            "4de13258303883538bd53b696b452bf8099f0858",
            "cls",
            "",
            "",
        ),
    )
}


# --- Embedding ------------------------------------------------------------------


def embed(tokenizer, session, texts: list[str], pooling: str) -> np.ndarray:
    """One row of unit length per text."""
    names = {model_input.name for model_input in session.get_inputs()}
    encoded = tokenizer.encode_batch(texts)
    token_ids = np.array([item.ids for item in encoded], dtype=np.int64)
    mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
    feed = {"input_ids": token_ids, "attention_mask": mask}
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.zeros_like(token_ids)
    token_vectors = session.run(None, feed)[0]

    if pooling == "cls":
        vectors = token_vectors[:, 0]
    else:
        weights = mask[..., np.newaxis]
        vectors = (token_vectors * weights).sum(axis=1) / weights.sum(axis=1)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def embed_in_batches(
    tokenizer, session, texts: list[str], pooling: str, batch: int
) -> np.ndarray:
    """The texts embedded `batch` at a time, one row per text, in order."""
    return np.vstack(
        [
            embed(tokenizer, session, texts[start : start + batch], pooling)
            for start in range(0, len(texts), batch)
        ]
    )


# --- Ranking --------------------------------------------------------------------


def rank_of_expected(scores: np.ndarray, section_keys: list, expected: list) -> int:
    """Where the best expected section stands when sections are sorted by score."""
    order = np.argsort(-scores)
    positions = [
        place
        for place, index in enumerate(order, start=1)
        if section_keys[index] in expected
    ]
    return min(positions)


def count_found(ranks: list[int]) -> dict:
    """How many questions find their section early, and how early on average.

    mrr is the mean of 1 / rank: 1 when every question finds its section first.
    """
    return {
        "first": sum(rank == 1 for rank in ranks),
        "top3": sum(rank <= 3 for rank in ranks),
        "top5": sum(rank <= 5 for rank in ranks),
        "mrr": round(sum(1 / rank for rank in ranks) / len(ranks), 3),
        "worst": max(ranks),
    }


# --- One model ------------------------------------------------------------------


def load(spec: ModelSpec):
    # Imported here so that the ranking code can be tested without them.
    import onnxruntime
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    def fetch(filename: str) -> str:
        return hf_hub_download(spec.repo, filename, revision=spec.revision)

    tokenizer = Tokenizer.from_file(fetch(TOKENIZER_FILE))
    tokenizer.enable_padding(pad_id=PAD_TOKEN_ID, pad_token=PAD_TOKEN)
    tokenizer.enable_truncation(max_length=MAX_TOKENS)
    options = onnxruntime.SessionOptions()
    # As in the product: no memory kept for the largest batch seen.
    options.enable_cpu_mem_arena = False
    session = onnxruntime.InferenceSession(
        fetch(MODEL_FILE), options, providers=["CPUExecutionProvider"]
    )
    return tokenizer, session


def measure(spec: ModelSpec, tokenizer, session, sections, questions, batches: str):
    # The questions are shared with the retrieval tests, so that the two
    # cannot drift apart.
    keys = [(section.file, section.number) for section in sections]
    passages = [spec.passage_prefix + section.embedding_text for section in sections]
    batch = len(passages) if batches == "all" else int(batches)
    matrix = embed_in_batches(tokenizer, session, passages, spec.pooling, batch)

    ranks, detail, milliseconds = [], [], []
    for rule, question, expected in questions:
        start = time.perf_counter()
        query = embed(tokenizer, session, [spec.query_prefix + question], spec.pooling)
        scores = matrix @ query[0]
        milliseconds.append((time.perf_counter() - start) * 1000)
        rank = rank_of_expected(scores, keys, expected)
        ranks.append(rank)
        best = np.argsort(-scores)[:TOP_SHOWN]
        detail.append(
            {
                "rule": rule,
                "question": question,
                "expected": [list(key) for key in expected],
                "rank": rank,
                "top": [
                    {
                        "section": f"{sections[index].file}#{sections[index].number}",
                        "score": round(float(scores[index]), 4),
                    }
                    for index in best
                ],
            }
        )
    return {
        "dimensions": int(matrix.shape[1]),
        **count_found(ranks),
        "query_ms_p50": round(statistics.median(milliseconds), 1),
        "query_ms_max": round(max(milliseconds), 1),
        "per_question": detail,
    }


def run_model(name: str) -> dict:
    """Measure one model in this process; the peak memory is read at the end."""
    from src.knowledge.policy_index import read_sections
    from tests.retrieval_questions import QUESTIONS

    spec = MODELS[name]
    tokenizer, session = load(spec)
    sections = read_sections()
    runs = {
        batches: measure(spec, tokenizer, session, sections, QUESTIONS, batches)
        for batches in BATCHES
    }
    return {
        "repo": spec.repo,
        "revision": spec.revision,
        "file": MODEL_FILE,
        "sections": len(sections),
        "questions": len(QUESTIONS),
        # ru_maxrss is in kilobytes on Linux.
        "peak_memory_mb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        ),
        "by_batch_size": runs,
    }


def run_in_own_process(name: str) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        output = Path(folder) / "result.json"
        subprocess.run(
            [sys.executable, __file__, "--child", name, "--output", str(output)],
            check=True,
        )
        return json.loads(output.read_text(encoding="utf-8"))


# --- Report ---------------------------------------------------------------------


def per_way(run_by_batch: dict, key: str) -> str:
    """A figure for each way of batching, written once where they agree."""
    values = [str(run_by_batch[batches][key]) for batches in BATCHES]
    return values[0] if len(set(values)) == 1 else " / ".join(values)


def markdown(results: dict) -> str:
    first = next(iter(results.values()))
    lines = [
        "# Embedding models on the policy questions",
        "",
        (
            f"{first['questions']} questions, {first['sections']} policy sections, "
            "quantized ONNX on CPU. A figure that differs between ways of embedding "
            "the sections is given as: all at once (as the policy index is built) / "
            "in batches of 10 / one at a time."
        ),
        "",
        "| Model | Vector | First | Top 3 | Top 5 | MRR | Worst rank | Query p50 (ms) | Peak memory (MB) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, result in results.items():
        runs = result["by_batch_size"]
        lines.append(
            f"| {name} | {runs[BATCHES[0]]['dimensions']} "
            f"| {per_way(runs, 'first')} | {per_way(runs, 'top3')} | {per_way(runs, 'top5')} "
            f"| {per_way(runs, 'mrr')} | {per_way(runs, 'worst')} | {per_way(runs, 'query_ms_p50')} | {result['peak_memory_mb']} |"
        )
    lines += ["", "## Revisions", ""]
    for name, result in results.items():
        lines.append(f"- {name}: `{result['repo']}` at `{result['revision']}`")
    return "\n".join(lines) + "\n"


# --- Command line ---------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=list(MODELS), help="one model")
    parser.add_argument("--list", action="store_true", help="list the models")
    parser.add_argument("--child", choices=list(MODELS), help=argparse.SUPPRESS)
    parser.add_argument("--output", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.list:
        for spec in MODELS.values():
            print(f"{spec.name:10} {spec.repo} ({spec.pooling} pooling)")
        return 0
    if args.child:
        Path(args.output).write_text(
            json.dumps(run_model(args.child), ensure_ascii=False), encoding="utf-8"
        )
        return 0

    names = [args.only] if args.only else list(MODELS)
    results = {}
    for name in names:
        print(f"measuring {name} ...", flush=True)
        results[name] = run_in_own_process(name)
    print(f"\n{terminal_tables(markdown(results))}")

    if not args.only:
        RESULTS_DIR.mkdir(exist_ok=True)
        (RESULTS_DIR / "embedding_compare_v1.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        (RESULTS_DIR / "embedding_compare_v1.md").write_text(
            markdown(results), encoding="utf-8"
        )
        print("Results written to eval/results/embedding_compare_v1.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
