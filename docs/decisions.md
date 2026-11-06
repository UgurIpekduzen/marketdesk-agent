# Decisions

The technology decisions that are expensive to change later, each with its reason. Every record has the same parts: the choice, the reasons, the alternatives, the costs and what would change it.

## Agent framework

LlamaIndex was chosen as the agent framework. LangGraph was the alternative that was looked at. The other options of the course guide (smolagents, Google ADK) were not compared in detail.

**Reasons**

- It takes plain Python functions as tools and has a step limit for the agent loop.
- It also covers the retrieval side. Policy search was first written directly on Chroma and was moved to LlamaIndex's `VectorStoreIndex` on 17 October, after a side-by-side comparison gave identical results.
- The aim was also to get to know one of the frameworks that are widely used in the job market, which matters for matching what employers look for in a portfolio. LlamaIndex and LangGraph seemed the most common of the frameworks the course guide suggests (smolagents, LlamaIndex, LangGraph, Google ADK). That was an impression and not a count.

**What was measured**

Small measurements made afterwards (one scenario, no real model) showed little difference to LangChain's `create_agent` on LangGraph and to Pydantic AI. A step takes 3.6 to 4.5 ms with LlamaIndex against 1.0 to 1.9 ms with the others. That is about 0.5% of the 751 ms a model call took in the development examples.

**Costs**

- It raises when it handles the output of the last allowed call, so the answer on the eighth call is not delivered.
- It runs synchronous tools in a worker thread, so the SQLite connection of the leak test had to be opened with `check_same_thread=False`.
- Its MCP client opens a new server process for every call, so the client was built on the `mcp` SDK instead.

The choice was tried and found harmless, not shown to be the best.

## Language model

`gemini-3.5-flash-lite` on the Gemini free tier was chosen as the model. Groq's `qwen/qwen3.8-27b` is the fallback, behind a flag (`LLM_USE_FALLBACK`) that is switched by hand.

**Reasons**

- The free tier left few candidates. According to the AI Studio rate-limit page on 5 November, the Flash models allow 20 requests a day and the Pro models none, while the Flash Lite models allow 500 and Gemma 4 allows 14,400.
- Of these, `gemini-3.5-flash-lite` was the only one that passed all ten scenarios in a one-run trial. The three Groq models passed 9, `gemini-3.1-flash-lite` (the same quota) gave four 503 errors, and `gemma-4-31b-it` gave 500 errors once tools were attached.
- It is also fast and cheap. A task takes 2.4 s of model time at p50 and about 0.0024 USD at the list price.

**Alternatives**

- Groq was not made the main model because its free plan allows 200K tokens a day (as read from the Groq console on 5 November), which does not fit a full evaluation run.
- Qwen was kept as the fallback after 9 of 10 in the same trial. It has not been run through the evaluation sets.

**Costs**

- The provider's 503 stretches inflated the latency measurements.
- The daily quota spread one evaluation over several days.
- The judge is the same model as the system.
- A change of model means running the evaluation again.
- The paid key was used only by evaluation and red team runs that were started with `--paid`. The page and the agents never use it.

**It would be changed if** the free quota ended, if quality fell in real use, or if the provider withdrew the model.

## Deployment

Streamlit Community Cloud was chosen to host the demo. It is the default of the course guide. Hugging Face Spaces was the alternative that was looked at.

**Reasons**

- It is free, opens at once from a GitHub repository and suits a page written in Streamlit.
- Hugging Face Spaces asks, according to the guide, for an account at least 30 days old with a verified e-mail. For a Streamlit app it also asks for Docker and so a paid plan.

**Fit**

The page process held 651 MB with the embedding model loaded and the container 1,412 MB in total, against a documented limit of 2.7 GB. That holds only because the embedding model runs as quantized ONNX (609 MB, against 1,068 MB for the same model with PyTorch).

**Costs**

- An app sleeps after 12 hours without visitors and takes about 50 seconds to wake.
- The demo database is built again at every start, so return requests begin empty.
- The platform's own image cannot be pinned.

**It would be changed if** the memory or the quota were not enough, if the free tier changed, or if real users came.

## Embedding model

`multilingual-e5-small`, as a quantized ONNX model run with ONNX Runtime, was chosen to embed the policy sections and the questions.

**Reasons**

- It was the course guide's suggestion for a light demo model.
- Its memory was the risk that mattered on the free platform: 609 MB for the model against 1,068 MB with PyTorch, and a page process of 651 MB with the model loaded.
- On the 20 Turkish questions it gave the right section in the top three for 18 (first for 14). The same 20 questions were also used to choose the text that is embedded for each section, so this is not an independent test.

**Alternatives**

It was chosen before the comparison of 31 October, which kept it.

- `e5-base` was not better (16 in the top three).
- `bge-m3` was a little better in Turkish (19 in the top three, a mean reciprocal rank of 0.87 against 0.81). It used about 660 MB more at its peak (1,344 MB against 676 MB). It was not tried on the platform, so it is not known that it would not fit.

**Costs**

- It is weak on English questions: 12 in the top three and a worst rank of 25 of 28, against 19 for `bge-m3`. The English questions are translations of the Turkish ones, and the policies are in Turkish only.
- The end-to-end results were measured with this model only.
- The index and the questions must use the same model, so a change means building the index again and running the evaluation again.
- The demo downloads the model from Hugging Face on its first start, which depends on the Hub being reachable. A read-only token is set in the secrets to raise the rate limit.

**It would be changed if** English policies or questions were needed, if memory were comfortably enough for `bge-m3`, or if the right section stopped reaching the top three.

## Python version

Python 3.12 was chosen, and the reason was not recorded.

**What was measured**

On 5 November 2026, in copies of the project, the locked dependencies (180 packages, the same versions) installed and the 2,764 unit tests and the 10 tests with the real embedding model passed on Python 3.13 and 3.14 as well. No dependency holds the version.

**Why it stays**

- It was chosen and tested.
- It is the default of Streamlit Community Cloud. The documentation of the platform lists no versions. It supports every version that still receives security updates, and the version is picked in the advanced settings of an app.

**What moving would mean**

- Setting the newer target for `ruff`: 8 findings on 3.13, and 9 findings and a format that only runs on 3.14.
- Checking the live page on the platform.
- Living with about 11,600 warnings on 3.14, all from dependencies, against 16.

**Costs**

- The newer language features are not used.
- No speed difference could be shown. In five runs of the unit tests per version, taken in turn after a warm-up run on 6 November, the medians were 84.8 s (79.1–91.8) on 3.12, 82.2 s (79.1–85.3) on 3.13 and 89.5 s (82.9–95.4) on 3.14. The ranges overlap. A first trial with three runs each had suggested that 3.13 is shorter, which the repeat does not show.

**It would be changed if** Python 3.12 stopped receiving security updates, if a dependency dropped it, or if the platform's default changed.

## Package management

`uv` was chosen as the only package manager, with `pyproject.toml` and the lock file `uv.lock`.

**Reasons**

- The lock gives the same versions in the container, in CI and on Streamlit Community Cloud. The 23 direct dependencies are pinned with `==` and the lock holds 180 packages.
- Its speed: resolving the 180 packages again for another Python version took 6 seconds in a trial. Against `pip` on 6 November (the project's requirements without `deepeval` and `deepteam`, which need a `uv` override for `click`: 21 requirements, 162 packages, three runs, resolution only), `uv` took 8.3 s (5.9–8.7) with an empty cache and `pip` 28.7 s (27.5–29.3). With a full cache they took 0.1 s and 6.0 s (4.7–6.0). No other tool was tried.

**Costs**

- `uv.lock` is the only dependency file kept, because the documentation of the platform says to use one file and reads the first it finds.
- The Python environment exists only in the container, with no `.venv` on the host. A dependency is added with `uv add --no-sync` and `task sync`.
- The platform's own image cannot be pinned, so only what `uv.lock` installs is under control.

**It would be changed if** the platform stopped reading `uv.lock` or if the tool gave trouble.

## Candidates

### Vector store

Chroma in file mode, used through LlamaIndex's `VectorStoreIndex` over `ChromaVectorStore`, was chosen to store and search the 28 policy sections. The search was first written directly on `chromadb` and was moved to LlamaIndex on 17 October with identical results.

**Reasons**

- It is a widely known vector database.
- It filters on metadata.
- It stores the text itself.
- It was expected to scale to a review corpus. That was not needed in the end, because only the policy sections are searched by vector.

**Alternatives**

Three other stores were measured on 7 October and again on 5 November with 300 synthetic vectors ([`vector_store_comparison.md`](vector_store_comparison.md)).

- FAISS has no metadata filter.
- LlamaIndex's `SimpleVectorStore` (164 MB of memory, 2.3 ms a search, with a filter) grows linearly. At 30,000 chunks it took 297 MB on disk, 43 seconds to load and 258 ms a search. Chroma at 30,000 chunks took 215 MB on disk, 0.07 seconds to open and 1.8 ms a search. Its process reached 984 MB while it built the index, and the same figure was not taken for `SimpleVectorStore`.
- `sqlite-vec` (one package, 0.11 ms a search) had no LlamaIndex connector tried.

**Costs**

- Chroma is the heaviest of the four: 56 more packages, 285 MB more on disk and 206 MB of memory against 164 MB.
- The index is kept in the repository (596 KB) and has to be built again when the embedding model changes.
- The scale was tried on random vectors only: Chroma and `SimpleVectorStore` up to 30,000 chunks, FAISS and `sqlite-vec` at 300. Chroma's search is approximate (HNSW), and it was not compared with an exact search on the policy sections. Only 28 sections are searched in the project. The LlamaIndex connector refuses more than 5,461 nodes in one call, so the measurement adds them in batches (the index of 28 sections is not affected).

**It would be changed if** memory or size came near the platform's limit, if the number of chunks grew a lot, or if Chroma gave trouble.

### SQL parser

`sqlglot` 30.21.0 was chosen to parse and check the free SQL of the operations session.

**Reasons**

- A real parser was needed. That is the rule of the project, not a regex.
- It parses a query into a tree and writes SQL out from it again. That is needed to add a `LIMIT` and to run the SQL that was checked and not the one that was received.
- Apache Superset introduced it to fix security issues and proposed to drop `sqlparse` (SIP-117, read on 6 November).
- It is widely used (DataHub builds its SQL parser on it, SQLMesh is in its list of users) and is written in pure Python with no dependency.

**Alternatives**

On 6 November they were tried in clean environments on 6 valid SQLite queries and on 7 queries that a validator has to see through, next to `sqlglot` 30.21.0. This shows what each can do, not how each would do in the whole validator.

- `sqlparse` is "a non-validating SQL parser". Version 0.6.1 parsed all 6 queries and never rejects a text. It finds function names and the `DELETE` as tokens, but builds no table model, has no scope analysis and cannot write SQL from a changed tree. Its README says that 0.6.1 (1 November 2026) was the final release.
- `sqloxide` 0.61.1 (compiled) reads the tree and writes it back with a changed `LIMIT`, but its SQLite grammar refused `GLOB` (5 of 6 parsed) and it has no scope analysis.
- `pglast` 8.7 (compiled, PostgreSQL's grammar) refused `GLOB` too (5 of 6), writes back with a changed `LIMIT` and has no scope analysis. It is not SQLite's grammar.
- `sqlfluff` 4.5.0 is a linter. All 6 queries parsed, but it cannot set a `LIMIT`, has no scope analysis and refused a `DELETE` inside a CTE as unparsable.
- Only `sqlglot` has a scope analysis. For `SELECT * FROM (WITH orders AS (SELECT 1 AS a) SELECT * FROM orders) AS q, orders` a plain search for tables finds `orders` twice, and the scope analysis finds the real table once.
- SQLite's authorizer can only allow, refuse or replace a column with NULL, so it cannot add a `LIMIT`.

**Costs**

The parser and SQLite do not always see the same thing.

- A trial before the design found three ways past a validator that only looks at the top of the tree: a `DELETE` inside a CTE, `pragma_table_info(...)` used as a table and `load_extension(...)` inside a plain `SELECT`.
- A CTE named like a real table inside a subquery would have let the outer query read the real table. So the whole tree is checked.
- One layer was not enough. The connection is read-only, `ATTACH` is limited to zero, a query may take 5 seconds and return 1,000 rows, a value may be 100,000 bytes and an answer 2,000,000, and the SQL that runs is written out again from the checked tree and checked a second time.
- The rule is also kept by hand. Functions the parser does not know are refused, except `julianday`, `datetime`, `time`, `unixepoch` and `total`.
- The red team still found that one free SQL query could build 900 MB in a second and that `sqlite_version()` was readable. Both were fixed afterwards.

**It would be changed if** a new difference between `sqlglot` and SQLite were found, if the project were dropped or a version broke the validator, or if free SQL were removed.

### Tracing

OpenTelemetry with the OpenInference instrumentation of LlamaIndex was chosen to record every run. The spans go to Arize Phoenix on the developer's machine and to Langfuse Cloud for the demo. The target is picked with `TRACING_TARGET` (off by default).

**Reasons**

- The instrumentation exists, so the code of the agents is not touched. Agent steps, model calls with token counts and tool calls come as spans.
- One vendor-neutral path lets a single masking exporter stand in front of both targets.
- Both tools are the ones the course guide names (Arize Phoenix, local and free, and Langfuse Cloud Hobby).

**Why both targets**

- Phoenix is local, free and sees the masked text. Its ports are bound to `127.0.0.1`.
- Langfuse is hosted, so the deployed page can send its traces to it and the page for the support representative can count error kinds from them. It gets only an allowlist of attributes (the kind of step, the names of the tool and the model, the token counts and the project's own attributes such as the error code), never a message text.

**Costs**

- The masking exporter is written and kept by the project. Raw ids become keyed hashes, and e-mail addresses, phone numbers, the city and zip code and the values of the secrets are removed from every span.
- The instrumentation does not make the spans of the project the current context (tried again on 6 November: a span opened inside a tool has no parent). So the decision of the rule engine and the result of the SQL check are read from the answer of the tool and written as attributes on the tool span instead.
- The order server process and the evaluation runs are not traced.
- On Langfuse an error can be read from its code but not from its text.

**It would be changed if** the free plan of Langfuse were not enough or changed, if the instrumentation stopped working with the version of LlamaIndex, or if real users came.

### Evaluation

An own runner (`eval/run_eval.py`) was chosen to run the examples, and DeepEval 4.2.8, a development dependency, to judge the answers.

**Reasons**

- DeepEval is the tool of the course guide.
- A ready metric (`FaithfulnessMetric`, `GEval`) was preferred to writing a judge from nothing. That was decided after the trade-offs were laid out.
- What the runner measures by rule is plain Python on the project's own results: the intent, the tool calls, the decision of the rule engine, the approval state, the match of the SQL result and the cited source.

**Alternatives**

- RAGAS was not tried. The guide says its maintenance slowed.
- A judge of the project's own was weighed against DeepEval and not chosen.
- No other tool was looked at.

**Costs**

- The judge is the same model as the system (`gemini-3.5-flash-lite`), so it grades its own work. A judge of another provider (`gpt-oss-120b` on Groq) exists and was used for the misinformation tests, not for the golden set.
- Its first setting was wrong. With all five policy documents as context it marked true sentences as unsupported (a faithfulness of 0.72). That became 0.95 when the context was cut to the documents the example names. The settings were found by reading its verdicts on the development examples.
- The hand check is small: 12 scores, 11 agreed (92%), and 10 of the 12 were full marks.
- DeepEval brought a conflict of versions. It caps `click` below 8.4 while `huggingface-hub` needs 8.4.2 or later. It was solved with an override, because `click` is used only by DeepEval's command line.
- DeepEval's pytest plugin is switched off, because it loaded the library and `.env` into every test run.

**It would be changed if** a conflict of versions became a big problem, if the scores of the judge were found not to be trusted, or if a larger or independent quota for the judge came.
