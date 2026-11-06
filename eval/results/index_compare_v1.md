# Policy search: direct Chroma and LlamaIndex

20 questions, 28 policy sections, multilingual-e5-small, 3 runs of 100 searches each. Times are the lowest and highest of the runs; a search includes embedding the query.

| | Direct Chroma | LlamaIndex |
|---|---|---|
| Same top 5 in the same order as direct | (reference) | 20 of 20 questions |
| Largest gap between two scores | (reference) | 0.0 |
| Search p50 (ms) | 5.2–6.3 | 5.9–7.2 |
| Search p95 (ms) | 7.7–8.3 | 8.3–11.3 |
| Opening the index (ms) | 15.7–17.9 | 17.9–20.8 |
| Building the index (ms) | 670.3–931.9 | 713.4–825.7 |
| Index on disk (KB) | 540 | 600 |
