# MarketDesk

<!-- TODO: final one-sentence description. -->
A customer-support and operations agent system for an online marketplace.

> **Status:** work in progress. The setup and data layer are in place; the rule engine, agents and UI are not built yet. See [Project status](#project-status).

## The problem

<!--
TODO: two or three short paragraphs: what happens in a marketplace support and
operations team today, where time and money are lost, and what MarketDesk
changes. Keep numbers for the cost section below.
-->

_To be written._

## Who it is for

<!--
TODO: one or two sentences per cell. "Today's problem" is what the person struggles
with now; "What MarketDesk does" is the concrete help they get.
-->

| Persona | Today's problem | What MarketDesk does |
|---|---|---|
| Customer | _To be written._ | _To be written._ |
| Support agent | _To be written._ | _To be written._ |
| Operations manager | _To be written._ | _To be written._ |

## Cost assumption

<!--
TODO: a measurable assumption with concrete numbers. A common shape:
- tickets per month, share that are "where is my order / can I return it"
- minutes per ticket today, hourly cost of a support agent
- expected share the agent resolves without a human, and the resulting saving
State clearly that these are assumptions, and where each number comes from.
-->

_To be written._

## Why an agent

<!--
TODO: answer the question directly: why can this problem not be solved
with a fixed workflow or a single LLM call? Points to cover: questions need different tools in different orders; some need several
steps; some need a clarifying question; decisions must come from rules and
data, not from the model.
-->

_To be written._

## Example questions

<!--
TODO: at least 10 questions, written in Turkish as a user would type them,
with mixed types. "Expected behaviour" is one short line: which path the
system should take, not the full answer.
-->

| # | Type | Question | Expected behaviour |
|---|---|---|---|
| 1 | Happy path (customer) | _To be written._ | _To be written._ |
| 2 | Happy path (customer) | _To be written._ | _To be written._ |
| 3 | Happy path (operations) | _To be written._ | _To be written._ |
| 4 | Multi-step | _To be written._ | _To be written._ |
| 5 | Multi-step | _To be written._ | _To be written._ |
| 6 | Ambiguous | _To be written._ | _To be written._ |
| 7 | Ambiguous | _To be written._ | _To be written._ |
| 8 | Out of scope | _To be written._ | _To be written._ |
| 9 | Attack | _To be written._ | _To be written._ |
| 10 | Attack | _To be written._ | _To be written._ |

## Tech stack

| Layer | Choice | Status |
|---|---|---|
| Language and packaging | Python 3.12, `uv` (`pyproject.toml` + `uv.lock`) | in use |
| Agent framework | LlamaIndex | pinned, not used yet |
| LLM | Gemini API free tier, Groq as fallback | keys set up, model to be chosen |
| MCP | `mcp` 2.x Python SDK, stdio transport, own server | pinned, not used yet |
| Database | SQLite | in use |
| Embedding | `intfloat/multilingual-e5-small` | planned |
| Vector store | Chroma | candidate |
| SQL validation | `sqlglot` | candidate |
| Tracing | OpenTelemetry + OpenInference, Phoenix locally | candidate |
| Evaluation | DeepEval | candidate |
| UI and deploy | Streamlit on Streamlit Community Cloud | planned |
| Local environment | Docker Compose, Task | in use |

The reasons behind each choice will be recorded in `docs/decisions.md`.

## Getting started

Requirements: [Docker](https://docs.docker.com/get-docker/) with Compose, and [Task](https://taskfile.dev/installation/). Python and `uv` run inside the container, so they do not need to be installed.

```bash
cp .env.example .env    # then fill in GEMINI_API_KEY and GROQ_API_KEY
task sync               # install dependencies from uv.lock
task data               # download Olist, load it into SQLite, verify it
task check              # lint and unit tests
```

`task data` needs no Kaggle account. It downloads about 120 MB, builds `data/marketdesk.db` and runs 42 checks against the expected row counts. `task check` needs no API key and no network.

Run `task` to list every command.

## Data and licence

- **Code:** MIT, see [LICENSE](LICENSE).
- **Data:** [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), licensed CC BY-NC-SA 4.0 (non-commercial, attribution required). The dataset and the database built from it are not part of this repository; `task data` fetches them.

"Today" in this project is fixed at 2018-09-01, shortly after the last orders in the dataset. Orders placed on or after that day are left out when the data is loaded.

## Project status

| Milestone | Scope | State |
|---|---|---|
| M0 Setup | Accounts, project skeleton, data download and load, smoke test | in progress |
| M1 Deterministic core | Return rule engine, order tools, approval flow, policies, metrics, SQL validator | not started |
| M2 Agent layer | Policy search, support agent, MCP server, operations agent, router, evaluation, tracing | not started |
| M3 Demo and delivery | Streamlit UI, full evaluation, attack tests, deploy | not started |

## Repository layout

```
config.py              settings (SIMULATED_TODAY)
data/download.py       downloads the dataset into data/raw/
scripts/               load_sqlite.py, smoke.py
src/                   rules, tools, mcp_server, knowledge, guardrails, agents
tests/                 unit tests on synthetic data
policies/  eval/  docs/
docker-compose.yaml    local environment
Taskfile.yml           every routine command
```
