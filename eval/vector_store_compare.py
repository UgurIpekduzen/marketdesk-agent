"""Vector stores, side by side: what each costs to install and to run.

Usage:  task vector:compare            (or, by hand:
        uv run python -m eval.vector_store_compare [--runs 3])

The project searches 28 policy sections through LlamaIndex over Chroma. This
script measures that choice against three other stores, with synthetic
vectors and no embedding model, so that the figures in docs/decisions.md can be
checked and repeated:

- LlamaIndex's own SimpleVectorStore (nothing to install beyond llama-index-core),
- Chroma, through the LlamaIndex connector the project uses,
- FAISS, through its LlamaIndex connector,
- sqlite-vec, raw (it has no LlamaIndex connector that was tried).

Every candidate runs in its own clean environment that uv builds for the
run (uv run --isolated --no-project --with ...), so that the packages it brings
can be counted and no candidate sees another's. FAISS and sqlite-vec are not
dependencies of the project; pyproject.toml and uv.lock stay as they are.

Measured, each three times (the median and the range are reported): the
packages and the disk the candidate adds to llama-index-core alone, the time to
build the environment with an empty cache and with a full one, the peak memory
of a process that adds 300 vectors of 384 dimensions and searches them, the
time of one search, and whether a search filtered on a metadata field returns
only matching items. For SimpleVectorStore the size, load time and search time
are also measured at 300, 3,000 and 30,000 chunks of 800 characters.

What this says: those figures, on one machine and one network, in one scenario.
What it does not say: anything about search quality (the stores here are exact
searches over random vectors), the embedding model, or how a store behaves
with real documents. The install times depend on the network.
"""

import argparse
import functools
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "eval" / "results"
THIS_FILE = Path(__file__).resolve()

PYTHON = "3.12"
DIMENSIONS = 384
CHUNKS = 300
QUERIES = 100
WARM_UP_QUERIES = 5
TOP_K = 5
SCALE_CHUNKS = (300, 3_000, 30_000)
SCALE_TEXT_CHARACTERS = 800
DEFAULT_RUNS = 3
RESULT_MARK = "RESULT "

CORE = "llama-index-core==0.14.25"


class Candidate:
    """A store to measure: the packages uv adds for it and what it is measured on."""

    def __init__(self, name: str, packages: list[str], with_core: bool):
        self.name = name
        self.packages = packages
        # Whether llama-index-core is in its environment, so that "extra" means
        # what it adds to core and not to a bare interpreter.
        self.with_core = with_core


CANDIDATES = [
    Candidate("llama-index-core only", [CORE], True),
    Candidate("SimpleVectorStore (LlamaIndex)", [CORE], True),
    Candidate(
        "Chroma (LlamaIndex connector)",
        [CORE, "llama-index-vector-stores-chroma==0.6.0", "chromadb==1.5.9"],
        True,
    ),
    Candidate(
        "FAISS (LlamaIndex connector)",
        [CORE, "llama-index-vector-stores-faiss==0.7.0", "faiss-cpu==1.15.1"],
        True,
    ),
    Candidate("sqlite-vec (raw)", ["sqlite-vec==0.1.9"], False),
]
BASE = CANDIDATES[0]


def worker_key(candidate: Candidate) -> str:
    """The short word the worker is started with."""
    return {
        "llama-index-core only": "base",
        "SimpleVectorStore (LlamaIndex)": "simple",
        "Chroma (LlamaIndex connector)": "chroma",
        "FAISS (LlamaIndex connector)": "faiss",
        "sqlite-vec (raw)": "sqlite-vec",
    }[candidate.name]


# --- Data ---------------------------------------------------------------------------


def synthetic_vectors(count: int, dimensions: int, seed: int) -> list[list[float]]:
    """Unit-length random vectors, the same for the same seed."""
    generator = random.Random(seed)
    vectors = []
    for _ in range(count):
        vector = [generator.gauss(0.0, 1.0) for _ in range(dimensions)]
        norm = sum(value * value for value in vector) ** 0.5
        vectors.append([value / norm for value in vector])
    return vectors


def category_of(index: int) -> str:
    """Half of the chunks are "a", half "b": the field a filtered search is tried on."""
    return "a" if index % 2 == 0 else "b"


def filter_holds(returned_ids: list[str]) -> bool:
    """Whether a search filtered on category "a" returned only category "a" items."""
    if not returned_ids:
        return False
    return all(category_of(int(item.removeprefix("n"))) == "a" for item in returned_ids)


# --- The command that starts one measurement ----------------------------------------


def uv_command(candidate: Candidate, *, cold: bool, arguments: list[str]) -> list[str]:
    """uv run in a clean environment with the candidate's packages added."""
    command = ["uv", "run", "--isolated", "--no-project", "--python", PYTHON]
    if cold:
        command.append("--no-cache")
    for package in candidate.packages:
        command += ["--with", package]
    # -I: no script directory and no environment variables in the module path,
    # so nothing in eval/ can shadow a package.
    return [*command, "python", "-I", *arguments]


def parse_result(output: str) -> dict | None:
    """The worker's result: the last line that starts with the mark."""
    for line in reversed(output.splitlines()):
        if line.startswith(RESULT_MARK):
            return json.loads(line[len(RESULT_MARK) :])
    return None


def seconds_to_build(candidate: Candidate, *, cold: bool) -> float:
    """The time uv takes to build the environment and start Python in it."""
    command = uv_command(candidate, cold=cold, arguments=["-c", "pass"])
    started = time.perf_counter()
    subprocess.run(command, check=True, capture_output=True, text=True)
    return time.perf_counter() - started


def run_worker(candidate: Candidate, arguments: list[str]) -> dict:
    """Run the measurement of one candidate in its own environment."""
    command = uv_command(
        candidate,
        cold=False,
        arguments=[str(THIS_FILE), "--worker", worker_key(candidate), *arguments],
    )
    done = subprocess.run(
        command, capture_output=True, text=True, cwd=PROJECT_ROOT, check=False
    )
    result = parse_result(done.stdout)
    if done.returncode != 0 or result is None:
        tail = " ".join(done.stderr.strip().splitlines()[-3:])
        return {"error": tail or f"exit code {done.returncode}"}
    return result


# --- Aggregation --------------------------------------------------------------------


def spread(values: list[float], digits: int = 2) -> dict:
    """Median, lowest and highest of the values."""
    return {
        "median": round(statistics.median(values), digits),
        "min": round(min(values), digits),
        "max": round(max(values), digits),
    }


def aggregate(runs: list[dict], fields: list[str]) -> dict:
    """The median and the range of each field over the runs that did not fail."""
    good = [run for run in runs if "error" not in run]
    if not good:
        return {"error": runs[0]["error"] if runs else "no run"}
    summary = {field: spread([run[field] for run in good]) for field in fields}
    summary["failed_runs"] = len(runs) - len(good)
    if "filter" in good[0]:
        summary["filter"] = good[0]["filter"]
    return summary


def cell(figure: dict, digits: int = 1) -> str:
    """A table cell: the median and, when the runs differ as shown, the range."""
    median = f"{figure['median']:.{digits}f}"
    low = f"{figure['min']:.{digits}f}"
    high = f"{figure['max']:.{digits}f}"
    if low == high:
        return median
    return f"{median} ({low}–{high})"


# --- Report -------------------------------------------------------------------------


def markdown(result: dict) -> str:
    """The results as a markdown report."""
    lines = [
        "# Vector stores, side by side",
        "",
        (
            f"{result['runs']} runs per figure (the median, and the range when the "
            f"runs differ). {result['chunks']} synthetic vectors of {DIMENSIONS} "
            "dimensions, "
            f"{QUERIES} searches for the top {TOP_K}, no embedding model, one machine, "
            f"Python {PYTHON}. Extra packages and disk are what a store adds to "
            "llama-index-core alone (sqlite-vec has no core: its figures are its own). "
            "The install times depend on the network. The searches are exact over "
            "random vectors: nothing here says how well a store finds the right "
            "section."
        ),
        "",
        (
            "| Store | Extra packages | Extra disk (MB) | Install, empty cache (s) "
            "| Install, full cache (s) | Peak memory (MB) | Search p50 (ms) "
            "| Metadata filter |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, row in result["stores"].items():
        if "error" in row:
            lines.append(f"| {name} | failed: {row['error']} | | | | | | |")
            continue
        lines.append(
            f"| {name} | {row['extra_packages']} | {cell(row['extra_disk_mb'])} "
            f"| {cell(row['install_cold_s'])} | {cell(row['install_cached_s'])} "
            f"| {cell(row['peak_memory_mb'], 0)} | {cell(row['search_ms_p50'], 2)} "
            f"| {row['filter']} |"
        )
    scale = result.get("scale")
    if scale:
        lines += [
            "",
            "## SimpleVectorStore as the chunks grow",
            "",
            (
                f"Chunks of {SCALE_TEXT_CHARACTERS} characters, the index kept with "
                "LlamaIndex's storage (the vector store and the document store as "
                "JSON files)."
            ),
            "",
            "| Chunks | Size on disk (MB) | Load (s) | Search p50 (ms) |",
            "|---|---|---|---|",
        ]
        for chunks, row in scale.items():
            label = f"{int(chunks):,}"
            if "error" in row:
                lines.append(f"| {label} | failed: {row['error']} | | |")
                continue
            lines.append(
                f"| {label} | {cell(row['size_mb'])} "
                f"| {cell(row['load_s'])} | {cell(row['search_ms_p50'], 1)} |"
            )
    lines += ["", "Versions: " + ", ".join(result["versions"]) + ".", ""]
    return "\n".join(lines) + "\n"


# --- The worker: runs inside the clean environment ----------------------------------


def installed_packages() -> tuple[int, float]:
    """The number of distributions in this environment and the disk they use (MB)."""
    from importlib import metadata

    names = set()
    size = 0
    for distribution in metadata.distributions():
        names.add(distribution.metadata["Name"])
        for file in distribution.files or []:
            path = Path(distribution.locate_file(file))
            if path.is_file():
                size += path.stat().st_size
    return len(names), size / 1_000_000


def peak_memory_mb() -> float:
    """Peak memory of this process, in MB."""
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def timed_searches(search, queries: list[list[float]]) -> float:
    """The median time of one search, in milliseconds, after a few warm-up searches."""
    for query in queries[:WARM_UP_QUERIES]:
        search(query)
    times = []
    for query in queries:
        started = time.perf_counter()
        search(query)
        times.append((time.perf_counter() - started) * 1000)
    return statistics.median(times)


def llama_nodes(vectors: list[list[float]], text: str = "chunk"):
    """LlamaIndex nodes holding the vectors."""
    from llama_index.core.schema import TextNode

    return [
        TextNode(
            id_=f"n{index}",
            text=text,
            embedding=vector,
            metadata={"category": category_of(index)},
        )
        for index, vector in enumerate(vectors)
    ]


def llama_filter():
    """A metadata filter in LlamaIndex form."""
    from llama_index.core.vector_stores.types import (
        FilterOperator,
        MetadataFilter,
        MetadataFilters,
    )

    return MetadataFilters(
        filters=[MetadataFilter(key="category", operator=FilterOperator.EQ, value="a")]
    )


def llama_search(store, query: list[float]):
    """Query a LlamaIndex vector store with one vector."""
    from llama_index.core.vector_stores.types import VectorStoreQuery

    return store.query(VectorStoreQuery(query_embedding=query, similarity_top_k=TOP_K))


def sqlite_search(connection, query: list[float]):
    """Query the sqlite-vec table with one vector."""
    import sqlite_vec

    return connection.execute(
        "SELECT rowid, distance FROM items WHERE embedding MATCH ? AND k = ?",
        (sqlite_vec.serialize_float32(query), TOP_K),
    ).fetchall()


def retrieve(retriever, query: list[float]):
    """Retrieve through a LlamaIndex retriever with one vector."""
    from llama_index.core import QueryBundle

    return retriever.retrieve(QueryBundle(query_str="q", embedding=query))


def measure_llama_store(store) -> dict:
    """Build, search and filter a LlamaIndex vector store through its own API."""
    from llama_index.core.vector_stores.types import VectorStoreQuery

    vectors = synthetic_vectors(CHUNKS, DIMENSIONS, seed=0)
    queries = synthetic_vectors(QUERIES, DIMENSIONS, seed=1)
    nodes = llama_nodes(vectors)

    started = time.perf_counter()
    store.add(nodes)
    build_ms = (time.perf_counter() - started) * 1000

    search_ms = timed_searches(functools.partial(llama_search, store), queries)
    try:
        answer = store.query(
            VectorStoreQuery(
                query_embedding=queries[0],
                similarity_top_k=TOP_K,
                filters=llama_filter(),
            )
        )
        works = filter_holds(list(answer.ids or []))
        filter_result = "works" if works else "returned other items"
    except (ValueError, NotImplementedError) as error:
        filter_result = f"not supported ({error})"
    return {
        "build_ms": build_ms,
        "search_ms_p50": search_ms,
        "filter": filter_result,
    }


def worker_simple() -> dict:
    """Measure SimpleVectorStore."""
    from llama_index.core.vector_stores import SimpleVectorStore

    return measure_llama_store(SimpleVectorStore())


def worker_chroma() -> dict:
    """Measure Chroma."""
    import tempfile

    import chromadb
    from llama_index.vector_stores.chroma import ChromaVectorStore

    with tempfile.TemporaryDirectory() as folder:
        client = chromadb.PersistentClient(path=folder)
        collection = client.create_collection(
            "compare", metadata={"hnsw:space": "cosine"}
        )
        return measure_llama_store(ChromaVectorStore(chroma_collection=collection))


def worker_faiss() -> dict:
    """Measure FAISS."""
    import faiss
    from llama_index.vector_stores.faiss import FaissVectorStore

    return measure_llama_store(
        FaissVectorStore(faiss_index=faiss.IndexFlatIP(DIMENSIONS))
    )


def worker_sqlite_vec() -> dict:
    """Measure sqlite-vec."""
    import sqlite3

    import sqlite_vec

    vectors = synthetic_vectors(CHUNKS, DIMENSIONS, seed=0)
    queries = synthetic_vectors(QUERIES, DIMENSIONS, seed=1)
    connection = sqlite3.connect(":memory:")
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    connection.execute(
        f"CREATE VIRTUAL TABLE items USING vec0(embedding float[{DIMENSIONS}])"
    )

    started = time.perf_counter()
    for index, vector in enumerate(vectors):
        connection.execute(
            "INSERT INTO items(rowid, embedding) VALUES (?, ?)",
            (index, sqlite_vec.serialize_float32(vector)),
        )
    build_ms = (time.perf_counter() - started) * 1000

    return {
        "build_ms": build_ms,
        "search_ms_p50": timed_searches(
            functools.partial(sqlite_search, connection), queries
        ),
        "filter": "not tried",
    }


WORKERS = {
    "base": lambda: {"build_ms": 0.0, "search_ms_p50": 0.0, "filter": "—"},
    "simple": worker_simple,
    "chroma": worker_chroma,
    "faiss": worker_faiss,
    "sqlite-vec": worker_sqlite_vec,
}


def scale_worker(chunks: int) -> dict:
    """SimpleVectorStore with real-sized chunks, kept to disk and loaded again."""
    import tempfile

    import numpy
    from llama_index.core import (
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
    )
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.schema import TextNode
    from llama_index.core.vector_stores import SimpleVectorStore

    generator = numpy.random.default_rng(0)
    matrix = generator.standard_normal((chunks, DIMENSIONS)).astype("float32")
    matrix /= numpy.linalg.norm(matrix, axis=1, keepdims=True)
    queries = synthetic_vectors(QUERIES, DIMENSIONS, seed=1)
    text = "x" * SCALE_TEXT_CHARACTERS
    embed_model = MockEmbedding(embed_dim=DIMENSIONS)
    nodes = [
        TextNode(
            id_=f"n{index}",
            text=text,
            embedding=row.tolist(),
            metadata={"category": category_of(index)},
        )
        for index, row in enumerate(matrix)
    ]
    with tempfile.TemporaryDirectory() as folder:
        context = StorageContext.from_defaults(vector_store=SimpleVectorStore())
        VectorStoreIndex(nodes, storage_context=context, embed_model=embed_model)
        context.persist(persist_dir=folder)
        size = sum(path.stat().st_size for path in Path(folder).iterdir()) / 1_000_000

        started = time.perf_counter()
        loaded = load_index_from_storage(
            StorageContext.from_defaults(persist_dir=folder), embed_model=embed_model
        )
        load_s = time.perf_counter() - started

        retriever = loaded.as_retriever(similarity_top_k=TOP_K)

        return {
            "size_mb": size,
            "load_s": load_s,
            "search_ms_p50": timed_searches(
                functools.partial(retrieve, retriever), queries
            ),
        }


def chroma_scale_worker(chunks: int) -> dict:
    """Chroma with real-sized chunks: built, kept to disk, opened again."""
    import tempfile

    import chromadb
    import numpy
    from llama_index.core.schema import TextNode
    from llama_index.vector_stores.chroma import ChromaVectorStore

    generator = numpy.random.default_rng(0)
    matrix = generator.standard_normal((chunks, DIMENSIONS)).astype("float32")
    matrix /= numpy.linalg.norm(matrix, axis=1, keepdims=True)
    queries = synthetic_vectors(QUERIES, DIMENSIONS, seed=1)
    text = "x" * SCALE_TEXT_CHARACTERS
    nodes = [
        TextNode(
            id_=f"n{index}",
            text=text,
            embedding=row.tolist(),
            metadata={"category": category_of(index)},
        )
        for index, row in enumerate(matrix)
    ]
    with tempfile.TemporaryDirectory() as folder:
        client = chromadb.PersistentClient(path=folder)
        collection = client.create_collection(
            "compare", metadata={"hnsw:space": "cosine"}
        )
        started = time.perf_counter()
        store = ChromaVectorStore(chroma_collection=collection)
        # One call takes at most this many records; the connector does not split.
        batch = client.get_max_batch_size()
        for start in range(0, len(nodes), batch):
            store.add(nodes[start : start + batch])
        build_s = time.perf_counter() - started
        size = sum(
            path.stat().st_size for path in Path(folder).rglob("*") if path.is_file()
        )

        # Chroma remembers the folders it has opened in this process: forget
        # them, so that the next client reads the files again.
        del collection
        client.clear_system_cache()
        started = time.perf_counter()
        reopened = chromadb.PersistentClient(path=folder).get_collection("compare")
        store = ChromaVectorStore(chroma_collection=reopened)
        llama_search(store, queries[0])
        load_s = time.perf_counter() - started

        return {
            "size_mb": size / 1_000_000,
            "build_s": build_s,
            "load_s": load_s,
            "search_ms_p50": timed_searches(
                functools.partial(llama_search, store), queries
            ),
            "peak_memory_mb": peak_memory_mb(),
        }


SCALE_WORKERS = {"simple": scale_worker, "chroma": chroma_scale_worker}


def worker_main(key: str, scale: int | None) -> int:
    """Run one measurement inside a worker process and print the result."""
    if scale is not None:
        result = SCALE_WORKERS[key](scale)
    else:
        result = WORKERS[key]()
        packages, disk_mb = installed_packages()
        result.update(
            {
                "packages": packages,
                "disk_mb": disk_mb,
                "peak_memory_mb": peak_memory_mb(),
            }
        )
    print(RESULT_MARK + json.dumps(result))
    return 0


# --- The driver ---------------------------------------------------------------------

STORE_FIELDS = ["search_ms_p50", "peak_memory_mb", "build_ms"]
SCALE_FIELDS = ["size_mb", "load_s", "search_ms_p50"]


def measure_store(candidate: Candidate, runs: int, base: dict | None) -> dict:
    """Install and measure one candidate, several runs."""
    print(f"measuring {candidate.name} ...", flush=True)
    cold = [seconds_to_build(candidate, cold=True) for _ in range(runs)]
    seconds_to_build(candidate, cold=False)  # fills the cache
    cached = [seconds_to_build(candidate, cold=False) for _ in range(runs)]
    results = [run_worker(candidate, []) for _ in range(runs)]
    summary = aggregate(results, STORE_FIELDS + ["packages", "disk_mb"])
    if "error" in summary:
        return summary
    base_packages = base["packages"] if base and candidate.with_core else 0
    own_packages = summary["packages"]["median"]
    base_disk = base["disk_mb"] if base and candidate.with_core else 0
    summary["extra_packages"] = int(own_packages - base_packages)
    summary["extra_disk_mb"] = {
        key: round(value - base_disk, 2) for key, value in summary["disk_mb"].items()
    }
    summary["install_cold_s"] = spread(cold)
    summary["install_cached_s"] = spread(cached)
    return summary


def measure_scale(runs: int) -> dict:
    """Measure SimpleVectorStore at growing numbers of chunks."""
    simple = next(item for item in CANDIDATES if item.name.startswith("Simple"))
    rows = {}
    for chunks in SCALE_CHUNKS:
        print(f"measuring SimpleVectorStore at {chunks:,} chunks ...", flush=True)
        results = [run_worker(simple, ["--scale", str(chunks)]) for _ in range(runs)]
        rows[str(chunks)] = aggregate(results, SCALE_FIELDS)
    return rows


CHROMA_SCALE_FIELDS = [
    "size_mb",
    "build_s",
    "load_s",
    "search_ms_p50",
    "peak_memory_mb",
]


def measure_chroma_scale(runs: int) -> dict:
    """Measure Chroma at growing numbers of chunks."""
    chroma = next(item for item in CANDIDATES if item.name.startswith("Chroma"))
    rows = {}
    for chunks in SCALE_CHUNKS:
        print(f"measuring Chroma at {chunks:,} chunks ...", flush=True)
        results = [run_worker(chroma, ["--scale", str(chunks)]) for _ in range(runs)]
        rows[str(chunks)] = aggregate(results, CHROMA_SCALE_FIELDS)
    return rows


def chroma_scale_markdown(result: dict) -> str:
    """The Chroma scale results as a markdown report."""
    lines = [
        "# Chroma as the chunks grow",
        "",
        (
            f"Chunks of {SCALE_TEXT_CHARACTERS} characters with random "
            f"{DIMENSIONS}-dimensional vectors, kept in Chroma's own folder through "
            f"the LlamaIndex connector. {result['runs']} runs per row, the median and "
            "the range. Load is opening the folder again and the first search."
        ),
        "",
        (
            "| Chunks | Size on disk (MB) | Build (s) | Load (s) | Search p50 (ms) "
            "| Peak memory (MB) |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for chunks, row in result["scale"].items():
        label = f"{int(chunks):,}"
        if "error" in row:
            lines.append(f"| {label} | failed: {row['error']} | | | | |")
            continue
        lines.append(
            f"| {label} | {cell(row['size_mb'])} | {cell(row['build_s'], 2)} "
            f"| {cell(row['load_s'], 2)} | {cell(row['search_ms_p50'], 1)} "
            f"| {cell(row['peak_memory_mb'], 0)} |"
        )
    lines += ["", "Versions: " + ", ".join(result["versions"]) + ".", ""]
    return "\n".join(lines) + "\n"


def run_chroma_scale(runs: int) -> dict:
    """The Chroma scale test with the versions it ran on."""
    return {
        "runs": runs,
        "scale": measure_chroma_scale(runs),
        "versions": versions_line(),
    }


def versions_line() -> list[str]:
    """The pinned package versions as text lines."""
    seen = dict.fromkeys(
        package for item in CANDIDATES for package in item.packages if package != CORE
    )
    return [CORE, *seen]


def run_all(runs: int) -> dict:
    """Measure every candidate and the scale test."""
    stores: dict[str, dict] = {}
    base_row = measure_store(BASE, runs, None)
    base = {
        "packages": base_row["packages"]["median"],
        "disk_mb": base_row["disk_mb"]["median"],
    }
    for candidate in CANDIDATES[1:]:
        stores[candidate.name] = measure_store(candidate, runs, base)
    return {
        "runs": runs,
        "chunks": CHUNKS,
        "base": {"packages": base["packages"], "disk_mb": round(base["disk_mb"], 1)},
        "stores": stores,
        "scale": measure_scale(runs),
        "versions": versions_line(),
    }


def main() -> int:
    """Run the command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--runs", type=int, default=DEFAULT_RUNS, help="runs per figure"
    )
    parser.add_argument("--worker", choices=sorted(WORKERS), help=argparse.SUPPRESS)
    parser.add_argument("--scale", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--chroma-scale",
        action="store_true",
        help="measure only Chroma at 300, 3,000 and 30,000 chunks",
    )
    args = parser.parse_args()

    if args.worker:
        return worker_main(args.worker, args.scale)

    if args.chroma_scale:
        from eval.terminal_table import terminal_tables

        result = run_chroma_scale(args.runs)
        print(f"\n{terminal_tables(chroma_scale_markdown(result))}")
        RESULTS_DIR.mkdir(exist_ok=True)
        stem = RESULTS_DIR / "vector_store_compare_chroma_scale_v1"
        stem.with_suffix(".json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        stem.with_suffix(".md").write_text(
            chroma_scale_markdown(result), encoding="utf-8"
        )
        print(f"Results written to {stem.relative_to(PROJECT_ROOT)}.json and .md")
        return 0

    from eval.terminal_table import terminal_tables

    result = run_all(args.runs)
    print(f"\n{terminal_tables(markdown(result))}")
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "vector_store_compare_v1.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (RESULTS_DIR / "vector_store_compare_v1.md").write_text(
        markdown(result), encoding="utf-8"
    )
    print("Results written to eval/results/vector_store_compare_v1.json and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
