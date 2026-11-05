# Vector stores, side by side

3 runs per figure (the median, and the range when the runs differ). 300 synthetic vectors of 384 dimensions, 100 searches for the top 5, no embedding model, one machine, Python 3.12. Extra packages and disk are what a store adds to llama-index-core alone (sqlite-vec has no core: its figures are its own). The install times depend on the network. The searches are exact over random vectors: nothing here says how well a store finds the right section.

| Store | Extra packages | Extra disk (MB) | Install, empty cache (s) | Install, full cache (s) | Peak memory (MB) | Search p50 (ms) | Metadata filter |
|---|---|---|---|---|---|---|---|
| SimpleVectorStore (LlamaIndex) | 0 | 0.0 | 62.3 (62.0–63.1) | 0.1 | 164 (155–166) | 2.30 (2.30–2.34) | works |
| Chroma (LlamaIndex connector) | 56 | 285.5 | 130.8 (126.1–159.0) | 0.1 | 206 (196–206) | 1.05 (1.03–1.07) | works |
| FAISS (LlamaIndex connector) | 2 | 66.2 | 76.5 (74.5–86.9) | 0.1 | 161 (157–166) | 0.02 | not supported (Metadata filters not implemented for Faiss yet.) |
| sqlite-vec (raw) | 1 | 0.2 | 1.9 (1.9–2.5) | 0.0 | 39 | 0.11 | not tried |

## SimpleVectorStore as the chunks grow

Chunks of 800 characters, the index kept with LlamaIndex's storage (the vector store and the document store as JSON files).

| Chunks | Size on disk (MB) | Load (s) | Search p50 (ms) |
|---|---|---|---|
| 300 | 3.0 | 0.4 | 2.5 |
| 3,000 | 29.7 | 4.0 (4.0–4.3) | 24.7 (24.1–24.9) |
| 30,000 | 297.3 | 43.1 (41.7–43.9) | 257.5 (256.9–257.7) |

Versions: llama-index-core==0.14.25, llama-index-vector-stores-chroma==0.6.0, chromadb==1.5.9, llama-index-vector-stores-faiss==0.7.0, faiss-cpu==1.15.1, sqlite-vec==0.1.9.

