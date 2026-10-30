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

## The comparison, measured again

The side-by-side comparison above was first made with code that was not kept. On 2026-10-31 it was rebuilt as a script that stays in the repository: `task index:compare` (`eval/index_compare.py`). It builds both indexes from the same vectors (the 28 sections in one batch, as the product builds its index), asks the 20 retrieval questions of `tests/test_retrieval.py`, and compares what comes back and what it costs. Times are the lowest and highest of three runs of 100 searches; a search includes embedding the query.

| | Direct Chroma | LlamaIndex |
|---|---|---|
| Same top 5 in the same order as direct | (reference) | 20 of 20 questions |
| Largest gap between two scores | (reference) | 0.0 |
| Search p50 (ms) | 5.2–6.3 | 5.9–7.2 |
| Search p95 (ms) | 7.7–8.3 | 8.3–11.3 |
| Opening the index (ms) | 15.7–17.9 | 17.9–20.8 |
| Building the index (ms) | 670–932 | 713–826 |
| Index on disk (KB) | 540 | 600 |

The results are those of 2026-10-17: the same sections in the same order, the same scores. The times differ in the same direction, by about a millisecond, but the ranges of the runs overlap, so this says LlamaIndex tends to be slower in a search, not that it is. The script does not measure memory; the figures for memory above are from 2026-10-17.

## What the framework adds to a step

`task eval:overhead` (`eval/framework_overhead.py`) runs the `FunctionAgent` of LlamaIndex through the project's own `run_agent` with the model taken out: a stand-in model (`tests/fakes.py`) answers at once and the one tool does nothing, so the time of a run is the framework's. A run asks for tools one after another and then answers; a run of n model calls has n - 1 tool calls. 200 runs per row after 5 warm-up runs, CPU.

| Model calls in a run | Run p50 (ms) | Run p95 (ms) | Step p50 (ms) | Step p95 (ms) |
|---|---|---|---|---|
| 1 | 4.6 | 6.0 | 4.6 | 6.0 |
| 2 | 8.6 | 10.4 | 4.3 | 5.2 |
| 4 | 16.2 | 18.8 | 4.1 | 4.7 |
| 7 (the longest run that ends with an answer) | 27.8 | 32.4 | 4.0 | 4.6 |

A step takes about 4 ms. Building the agent and its context takes about 0.7 ms, once per session. A run of eight calls is not in the table because it does not end with an answer: LlamaIndex stops with "Max iterations reached" when it handles the output of the eighth call, even if that is the answer, and `run_agent` then returns the step-limit message (a test records this). In the 25 development examples of the golden set the model took 751 ms per call (83 calls, from the results file), so the framework's step is about 0.53% of it.

Read with care: the figure includes the project's own `run_agent` and the stand-in's bookkeeping (it records every request). Measured without them (the bare `agent.run` and a stand-in that records nothing, in the comparison below), a step took 3.6 to 4.4 ms, so the two add little. The figure leaves out the real tools, the network, the guard around the model and tracing. Two other frameworks are measured in the next section, and only there. The figures found on the web (about 6 ms for LlamaIndex and 14 ms for LangGraph) come from a benchmark by AIMultiple (January 2026) of a whole RAG workflow, per query, with several model calls and a graph of steps; its method is described, but its library versions, hardware, spread and raw data are not published, and a comparison page by Metavert repeats the figures without naming a source. They are per query and not per model call, so they cannot be set against the figures here, and they are not used.

## Three frameworks side by side

`task eval:overhead:compare` (`eval/framework_compare.py`) runs the same scenario for LlamaIndex (the bare `agent.run`, and through `run_agent`), for Pydantic AI and for LangChain's `create_agent`, which runs on LangGraph, in one process, with a scripted model that answers at once and a tool that does nothing. LangGraph's own `create_react_agent` is deprecated in favour of `create_agent` (it warns so, to be removed in LangGraph 2.0), so `create_agent` was used. Pydantic AI (`pydantic-ai-slim` 2.63.0, its own `FunctionModel`) and LangChain (`langchain` 1.4.7 with `langgraph` 1.2.19 and `langchain-core` 1.7.3, a scripted chat model that answers in its async path directly) are not dependencies of the project: the task adds them for the run only, and `pyproject.toml` and `uv.lock` stay as they are. 200 runs per row after 5 warm-up runs, CPU. The LlamaIndex stand-in here records nothing.

| Way | Step p50 (ms), for 1 / 2 / 4 / 7 model calls | Step p95 (ms), the same | Run of 7 calls, p50 / p95 (ms) | Building the agent, p50 (ms) |
|---|---|---|---|---|
| LlamaIndex, bare agent.run | 4.4 / 4.0 / 3.8 / 3.6 | 6.2 / 5.8 / 4.3 / 4.1 | 24.9 / 28.4 | 0.6–0.7 |
| LlamaIndex, through run_agent | 4.5 / 4.2 / 4.0 / 3.8 | 5.0 / 5.2 / 5.0 / 4.6 | 26.7 / 31.9 | 0.6–0.7 |
| Pydantic AI 2.63.0 | 1.9 / 1.6 / 1.5 / 1.4 | 2.3 / 1.9 / 1.6 / 1.5 | 9.7 / 10.6 | 0.5–0.6 |
| LangChain 1.4.7 create_agent (on LangGraph) | 1.0 / 1.1 / 1.1 / 1.1 | 1.3 / 1.4 / 1.5 / 1.3 | 7.9 / 8.9 | 2.3–2.5 |

In this scenario a LlamaIndex step takes about 3.6 to 4.5 ms, a Pydantic AI step about 1.4 to 1.9 ms and a LangChain-on-LangGraph step about 1.0 to 1.1 ms; building the LangChain agent (it compiles a graph) takes about 2.3 ms against 0.6 ms for LlamaIndex, once per session. All of them are small against the 751 ms the model took per call. Read with care: it is one scenario, on the CPU, with no tracing, no real tools and no real model; the frameworks do different work around a step (LlamaIndex runs an event workflow with a context that can be saved, LangGraph keeps a state and can checkpoint it), so a faster step is not a better framework; and the figures say nothing about quality, features or memory. The scripted models are not the same code, and a different way of scripting one could move a figure.

## Embedding models

The policy search uses `multilingual-e5-small`, quantized. `task embed:compare` (`eval/embedding_compare.py`) runs three models on the same 20 retrieval questions and the same 28 section texts, with cosine similarity, each model in a process of its own: `multilingual-e5-small` (118 MB), `multilingual-e5-base` (279 MB) and `bge-m3` (570 MB), all as quantized ONNX from pinned revisions of the `Xenova` repositories. E5 models get the prefixes "query: " and "passage: " and mean pooling; `bge-m3` gets no prefix and the first token's vector. The measure is the rank of the best expected section among all 28 (1 = first).

The quantized models give a text a slightly different vector depending on which texts are embedded with it (see above), so every model is run three ways: all sections at once (as the product builds its index), in batches of 10, and one at a time. The tables give the first way, and in brackets the lowest and highest over the three.

**Questions in Turkish** (`eval/results/embedding_compare_v1.md`):

| Model | First | Top 3 | Top 5 | MRR | Worst rank | Query p50 | Process peak memory |
|---|---|---|---|---|---|---|---|
| e5-small | 14 (14–15) | 18 (17–18) | 18 | 0.806 (0.793–0.822) | 8 (8–9) | 2.3 ms | 676 MB |
| e5-base | 13 (13–16) | 16 (16–17) | 17 (17–19) | 0.746 (0.746–0.852) | 8 (6–11) | 6.8 ms | 928 MB |
| bge-m3 | 16 (16–17) | 19 | 19 (19–20) | 0.872 (0.872–0.893) | 9 (5–9) | 22.3 ms | 1344 MB |

**The same questions in English** (`eval/results/embedding_compare_en_v1.md`): the 20 questions translated, with the same expected sections. The policies stay Turkish.

| Model | First | Top 3 | Top 5 | MRR | Worst rank | Query p50 | Process peak memory |
|---|---|---|---|---|---|---|---|
| e5-small | 7 (6–8) | 12 (12–14) | 15 (14–15) | 0.515 (0.483–0.572) | 25 (14–25) | 3.7 ms | 678 MB |
| e5-base | 11 (11–12) | 18 (16–18) | 19 (18–19) | 0.722 (0.713–0.735) | 14 (7–14) | 7.0 ms | 921 MB |
| bge-m3 | 17 (14–17) | 19 (19–20) | 19 (19–20) | 0.892 (0.817–0.892) | 6 (3–6) | 21.7 ms | 1340 MB |

What the numbers show:

- With the product's own way of embedding, `multilingual-e5-small` gives the same 14 / 18 / 18 as `tests/test_retrieval.py`, which checks that the script follows the product's search.
- In Turkish, `bge-m3` finds the expected section in the top three for 19 of 20 questions, `e5-small` for 18 (17 in the other two ways) and `e5-base` for 16 (16–17). The mean reciprocal rank is 0.87, 0.81 and 0.75.
- In English, `e5-small` falls to 12 in the top three (12–14), 15 in the top five, and its worst rank is 25 of 28. `e5-base` holds 18 (16–18); `bge-m3` 19 (19–20).
- A query costs about 2.3 ms with `e5-small`, 6.8 ms with `e5-base` and 22 ms with `bge-m3`. The process peak memory (the model, the runtime and the three runs of embedding) is 676, 928 and 1,344 MB. `bge-m3` was not tried on the deployment platform.
- The support agent is told to search in Turkish (the tool's description says "query is the question in Turkish"), but the instruction is not always followed: the response cache of the evaluation runs holds 175 different search queries, and by a list of common words 155 are Turkish, 15 English, 3 mixed and 2 unclear. The cache does not record which session a query came from, so how often an English-session question stays English was not measured. English queries do reach the search, so the English run shows a real case, not only a possible one.
- The `bge-m3` code was checked against Xenova's own export with pooling inside it (`sentence_transformers_quantized.onnx`): on 48 texts the cosine between the two vectors was 1.0000 at the lowest, and 0.67 at the lowest (0.74 on average) when mean pooling was used instead, so the check could have failed. Both use the same quantized weights, so it does not measure what quantizing costs against the full model.

## Limits

- 20 questions is a small sample: one question moves a figure by 5 points. Three of the 20 are questions the policies do not answer; the right result for them is the section that says so.
- The batch effect of the quantized models is of the size of the differences between the models in places (`e5-base`, first: 13 to 16). The figures are a direction, not a ranking beyond doubt.
- The English questions are translations of the Turkish ones.
- Only the product's model (`e5-small`) was run through the whole evaluation: the policy faithfulness of 0.95 and the other end-to-end figures do not say what another embedding model would give.
- Two other agent frameworks (Pydantic AI, and LangChain on LangGraph) were measured, in one scenario of the agent loop and nowhere else; no other framework was measured, and none in search.

## Traces

The LlamaIndex search adds two kinds of spans to a trace: embedding (the query turned into a vector) and retrieval (the sections found). They were checked against both tracing targets, by sending real traces and reading back what each server stored.

- **Langfuse** stored the spans with their kind and the service and library name only: no input or output, no query, no section text, no vector. The allowlist of attributes for hosted targets did this without a change.
- **Phoenix** (local only) stored the query and the sections, masked as before. It also stored the query vector, which is computed from the unmasked text, out of reach of the masking. Hiding vectors with OpenInference's `TraceConfig(hide_embedding_vectors=True)` removed them, kept every other attribute, and made the stored trace of a search about half the size (22.7 KB against 47.6 KB for three searches). Search time with and without vectors differed by less than its own spread. Vectors are now hidden for every target.

Tests in `tests/test_tracing.py` hold this: a hosted target gets no text or vector of a search, a raw id in a query is masked locally, and no target gets a vector. Each test was checked by breaking the code it guards and watching it fail.

## Decision

The author decided on 2026-10-17 to move to LlamaIndex and remove the direct Chroma code.

## How to measure again

`task test:model` checks the retrieval numbers of the table of 2026-10-17 with the real model. `task index:compare` repeats the comparison of direct Chroma with LlamaIndex, `task eval:overhead` the measurement of what the framework adds to a step (no model, no key), and `task eval:overhead:compare` the same for LlamaIndex, Pydantic AI and LangChain on LangGraph (the last two are added for the run only), and `task embed:compare` the comparison of the embedding models (about 970 MB downloaded once; `-- --language en` for the English questions). The old direct Chroma code is in the history before the commit "refactor: search the policies through LlamaIndex"; the comparison script has its own copy of it.
