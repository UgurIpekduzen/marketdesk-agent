# Policy search: direct Chroma and LlamaIndex

The policy search first used Chroma directly through `chromadb`. On 2026-10-17 it moved to LlamaIndex: `VectorStoreIndex` over `ChromaVectorStore` (`llama-index-vector-stores-chroma` 0.6.0). Both versions were run side by side before the old one was removed. This page records what was measured.

Everything else was held equal: the 28 policy sections, the embedding model (`multilingual-e5-small`, quantized ONNX), the text that is embedded, cosine distance, the score scale and the shape of a result. Only the layer that stores and searches the vectors differed.

## What had to be done to keep the results equal

- **The embedded text.** LlamaIndex puts a node's metadata in front of its text as `key: value` lines. The node templates are set so that the embedded text stays "document title: section heading" followed by the section text, as before. A test compares the two for every section.
- **The score.** `ChromaVectorStore` reports `exp(-distance)` as the score. The distance is taken back from it, so the score is still the cosine similarity. A test checks the score against the cosine computed directly.
- **The batch.** The quantized model gives a text a slightly different vector depending on which other texts are embedded with it: between one batch of 28 and batches of 10, a coordinate moved by up to 0.015; between one batch of 28 and one text at a time, by up to 0.014, and the lowest cosine between the two vectors of one section was 0.9965. LlamaIndex embeds in batches of 10 by default; the old index embedded all 28 sections at once. The new index embeds them in one batch too: its 28 stored vectors are identical to the old index's, with no difference in any coordinate. A test checks the batch size.

## Results

Measured in the development container on CPU. Where a number varied between runs (three runs for the times), the range is given.

| | Direct Chroma | LlamaIndex |
|---|---|---|
| Expected section first / in the top 3 / in the top 5 (20 questions) | 14 / 18 / 18 | 14 / 18 / 18 |
| Same top 5 sections and scores | — | 20 of 20 questions |
| Search time p50 / p95 (100 searches per run) | 5.0–5.3 / 6.2–8.4 ms | 6.1–6.6 / 9.1–10.1 ms |
| Opening the index | 0.1 s | 0.2 s |
| Building the index (28 sections) | 0.8–1.0 s | 0.9–1.0 s |
| Index on disk | 540 KB | 596 KB |
| Memory to open and search, in the page after an agent has run | 21.6 MB | 21.7 MB |

**End to end.** The golden set with the judge, the baselines with the judge and the attack set were run again with the LlamaIndex index, from the response cache only and with every live model call made to fail. Not one request missed the cache: every prompt the model would see was the same as in the recorded run, and so were the results. The only difference in the results files was the counter of live calls.

**Memory, read with care.** Measured alone, the LlamaIndex index took about 33 MB more. That is `tiktoken`, which LlamaIndex loads for a default text splitter the index does not use. The agents' chat memory loads `tiktoken` as well, so in the running page the cost is already paid; measured after the chat memory was created, the two versions differ by 0.1 MB.

## Traces

The LlamaIndex search adds two kinds of spans to a trace: embedding (the query turned into a vector) and retrieval (the sections found). They were checked against both tracing targets, by sending real traces and reading back what each server stored.

- **Langfuse** stored the spans with their kind and the service and library name only: no input or output, no query, no section text, no vector. The allowlist of attributes for hosted targets did this without a change.
- **Phoenix** (local only) stored the query and the sections, masked as before. It also stored the query vector, which is computed from the unmasked text, out of reach of the masking. Hiding vectors with OpenInference's `TraceConfig(hide_embedding_vectors=True)` removed them, kept every other attribute, and made the stored trace of a search about half the size (22.7 KB against 47.6 KB for three searches). Search time with and without vectors differed by less than its own spread. Vectors are now hidden for every target.

Tests in `tests/test_tracing.py` hold this: a hosted target gets no text or vector of a search, a raw id in a query is masked locally, and no target gets a vector. Each test was checked by breaking the code it guards and watching it fail.

## Decision

The author decided on 2026-10-17 to move to LlamaIndex and remove the direct Chroma code.

## How to measure again

`task test:model` checks the retrieval numbers above with the real model. The side-by-side comparison needed both versions in the code and is not kept; the old version is in the history before the commit "refactor: search the policies through LlamaIndex".
