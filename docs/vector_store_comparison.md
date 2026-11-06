# Vector stores: install, memory and search

The policy search keeps its 28 sections in Chroma, through LlamaIndex (see [`policy_search_comparison.md`](policy_search_comparison.md) for the move from direct Chroma to LlamaIndex, and [`decisions.md`](decisions.md) for the reasons). This page records what the choice costs compared with three other stores. The figures were first taken by hand on 7 October 2026 (one run each) and were repeated on 5 November 2026 with `task vector:compare` (three runs each, the median and the range), twice: once before and once after the script was tidied, which gave the same figures except for the install times. The script is `eval/vector_store_compare.py`. Its raw results are in [`eval/results/vector_store_compare_v1.md`](../eval/results/vector_store_compare_v1.md) and `.json`.

## What was measured

Four stores, each in its own clean environment that `uv` builds for the run, so that the packages a store brings can be counted and no store sees another's:

- LlamaIndex's `SimpleVectorStore` (nothing beyond `llama-index-core`),
- Chroma (`chromadb` 1.5.9, through `llama-index-vector-stores-chroma` 0.6.0), the one in use,
- FAISS (`faiss-cpu` 1.15.1, through `llama-index-vector-stores-faiss` 0.7.0),
- `sqlite-vec` 0.1.9, raw: no LlamaIndex connector for it was tried.

The data are 300 random vectors of 384 dimensions (the size of `multilingual-e5-small`) with a `category` field on each, and 100 searches for the top 5. No embedding model is loaded. FAISS and `sqlite-vec` are not dependencies of the project: the task adds them for the run only, and `pyproject.toml` and `uv.lock` stay as they are.

## Results of 5 November (second run)

| Store | Extra packages | Extra disk (MB) | Install, empty cache (s) | Install, full cache (s) | Peak memory (MB) | Search p50 (ms) | Metadata filter |
|---|---|---|---|---|---|---|---|
| SimpleVectorStore | 0 | 0 | 62.3 (62.0–63.1) | 0.1 | 164 (155–166) | 2.30 (2.30–2.34) | works |
| Chroma | 56 | 285.5 | 130.8 (126.1–159.0) | 0.1 | 206 (196–206) | 1.05 (1.03–1.07) | works |
| FAISS | 2 | 66.2 | 76.5 (74.5–86.9) | 0.1 | 161 (157–166) | 0.02 | not supported |
| `sqlite-vec` | 1 | 0.2 | 1.9 (1.9–2.5) | 0.0 | 39 | 0.11 | not tried |

"Extra" is what a store adds to `llama-index-core` alone (62 packages, 176 MB). `sqlite-vec` has no core, so its figures are its own. The filter is a search for category "a" that has to return only items of that category. FAISS's LlamaIndex connector refuses it with "Metadata filters not implemented for Faiss yet."

`SimpleVectorStore` as the number of chunks grows (chunks of 800 characters, kept with LlamaIndex's storage as JSON files):

| Chunks | Size on disk (MB) | Load (s) | Search p50 (ms) |
|---|---|---|---|
| 300 | 3.0 | 0.4 | 2.5 |
| 3,000 | 29.7 | 4.0 | 24.7 |
| 30,000 | 297.3 | 43.1 | 257.5 |

## Chroma as the chunks grow

On 6 November the same growth test was run for Chroma with `task vector:compare -- --chroma-scale` (three runs, the median and the range). The vectors are random, the chunks 800 characters, and Chroma keeps its own folder, through the LlamaIndex connector. "Load" is opening the folder again and the first search.

| Chunks | Size on disk (MB) | Build (s) | Load (s) | Search p50 (ms) | Peak memory (MB) |
|---|---|---|---|---|---|
| 300 | 3.1 | 0.13 (0.12–0.14) | 0.04 (0.03–0.04) | 1.1 | 210 (206–211) |
| 3,000 | 32.8 | 1.17 (1.13–1.23) | 0.02 (0.02–0.03) | 1.2 (1.2–1.3) | 305 (304–311) |
| 30,000 | 214.8 | 14.36 (14.13–14.88) | 0.07 (0.07–0.08) | 1.8 (1.6–2.0) | 984 (981–993) |

- At 30,000 chunks Chroma takes less disk (215 MB against 297 MB), opens in 0.07 seconds against 43 seconds, and searches in 1.8 ms against 258 ms. Its search is approximate (HNSW) and `SimpleVectorStore`'s is exact. The quality of the approximate search was not compared.
- The peak memory is that of the whole worker process, which also builds the 30,000 nodes (Python lists of 384 floats), so it is an upper bound for a store that is only opened and searched. The same figure was not taken for `SimpleVectorStore`.
- The LlamaIndex connector refused to add 30,000 nodes in one call ("Batch size of 30000 is greater than max batch size of 5461"). The measurement adds them in batches of the client's limit. The index of the 28 policy sections is far below it.
- The raw results are in [`eval/results/vector_store_compare_chroma_scale_v1.md`](../eval/results/vector_store_compare_chroma_scale_v1.md) and `.json`.

## Against the figures of 7 October

| | 7 October (one run) | 5 November (median of three, second run) |
|---|---|---|
| Chroma: extra packages / extra disk | 53 / 282 MB | 56 / 285.5 MB |
| FAISS: extra packages / extra disk | 2 / 64 MB | 2 / 66.2 MB |
| `sqlite-vec`: packages / disk | 1 / 1 MB | 1 / 0.2 MB |
| Search p50: Simple / Chroma / FAISS / `sqlite-vec` (ms) | 2.4 / 1.1 / 0.02 / 0.12 | 2.30 / 1.05 / 0.02 / 0.11 |
| Peak memory: Simple / Chroma / FAISS / `sqlite-vec` (MB) | 114 / 165 / 149 / 41 | 164 / 206 / 161 / 39 |
| Install with an empty cache: core / Chroma / FAISS (s) | 25.7 / 55.5 / 17.5 | 62.3 / 130.8 / 76.5 (first run: 17.5 / 53.6 / 23.0) |
| `SimpleVectorStore` at 30,000 chunks: size / load / search | 283 MB / 38 s / 312 ms | 297 MB / 43 s / 258 ms |

The package counts, the disk, the search times and the filter result are the same within about 10%. Two figures differ for known reasons:

- **Peak memory.** It is higher for every store, by about 40 MB, because the script's worker also imports LlamaIndex's node and filter classes. The difference between Chroma and `SimpleVectorStore` is about the same as before (51 MB on 7 October, 42 MB on 5 November).
- **Install times.** They depend on the network and the state of `uv`'s cache, and they moved a lot. With an empty cache the second run took 62, 131 and 77 seconds where the first, an hour earlier, took 18, 54 and 23. The order of the stores stayed the same: Chroma slowest, FAISS next, the core alone fastest. The 7 October times are one run each.

The packages, the disk, the search times and the filter result did not move between the two runs on 5 November.

## What this says and what it does not

It says what each store costs to install and to run in this scenario: on one machine and one network, with random vectors, 300 chunks and exact search. At the 28 sections of the policy search all four stores answer in under 3 ms, so search speed does not separate them. What separates them is:

- The install (Chroma brings 56 packages and about 285 MB).
- The memory.
- The metadata filter (FAISS has none).
- The growth (at 30,000 chunks `SimpleVectorStore` loads in 43 seconds and searches in 258 ms, and Chroma opens in 0.07 seconds and searches in 1.8 ms).

It does not say anything about the quality of the search. The searches are exact over random vectors, and no store was tried on the policy sections or with an embedding model here.

- Chroma's own search is approximate (HNSW). That was not compared with an exact search on the policy sections.
- The scale of 30,000 chunks was measured for `SimpleVectorStore` and Chroma, on random vectors. FAISS and `sqlite-vec` were not measured at that size. Nothing larger than 28 sections was searched in Chroma in this project.
