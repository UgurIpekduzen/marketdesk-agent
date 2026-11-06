# Chroma as the chunks grow

Chunks of 800 characters with random 384-dimensional vectors, kept in Chroma's own folder through the LlamaIndex connector. 3 runs per row, the median and the range. Load is opening the folder again and the first search.

| Chunks | Size on disk (MB) | Build (s) | Load (s) | Search p50 (ms) | Peak memory (MB) |
|---|---|---|---|---|---|
| 300 | 3.1 | 0.13 (0.12–0.14) | 0.04 (0.03–0.04) | 1.1 | 210 (206–211) |
| 3,000 | 32.8 | 1.17 (1.13–1.23) | 0.02 (0.02–0.03) | 1.2 (1.2–1.3) | 305 (304–311) |
| 30,000 | 214.8 (214.7–214.8) | 14.36 (14.13–14.88) | 0.07 (0.07–0.08) | 1.8 (1.6–2.0) | 984 (981–993) |

Versions: llama-index-core==0.14.25, llama-index-vector-stores-chroma==0.6.0, chromadb==1.5.9, llama-index-vector-stores-faiss==0.7.0, faiss-cpu==1.15.1, sqlite-vec==0.1.9.

