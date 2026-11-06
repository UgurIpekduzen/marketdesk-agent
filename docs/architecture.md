# Architecture

What each part of the system does, in the order a message meets it. The diagram is in the [README](../README.md#architecture). The reasoning behind the choices is in [`questions.md`](questions.md).

## The path of one message

1. **The page** (`app.py`, `src/ui/`) draws the chat and passes clicks on. It holds no business logic. The session type (customer, operations or support representative) and, for a customer, the identity are fixed when the session starts, never read from a message.
2. **The chat session** (`src/ui/chat_session.py`) belongs to one visitor session and runs the agent in the background. The message length, the questions an hour and the model calls a day are limited here, for all visitors together.
3. **The router** (`src/orchestrator.py`) classifies the message with one model call into `support`, `ops_metric`, `review_insight` or `out_of_scope`. Whether the session may have that class is not left to the classifier: a fixed table (`ALLOWED_INTENTS`) lists the classes of each session type, and anything else gets a fixed refusal text without an agent.
4. **The agent** answers with its own tools only, in a limited loop: at most 8 steps, the same tool with the same arguments at most twice, at most 2 SQL corrections.
5. **The answer** is checked before it is shown where code can check it: the critic compares the numbers with the tool output, and the theme check compares the quotes with the reviews.

## Sessions and who may do what

| Session | Classes it may have | Agent | What it can reach |
|---|---|---|---|
| Customer | `support` | Support Agent | the order tools through the customer's own MCP server, policy search, hand-over to a person. Never `run_sql`, `run_metric` or `summarize_reviews` |
| Operations | `ops_metric`, `review_insight` | Ops Data Agent, Review Insight Agent | metrics, checked read-only SQL, review themes. No order tools |
| Support representative | none (no model) | – | the queue of return requests and tickets, held only by that session |

Each agent holds only its own tools, so a classifier that was fooled still cannot reach the operations tools from a customer session.

## The customer side

- **The order server** (`src/mcp_server/server.py`, client in `client.py`) is started once for each customer session, speaks over stdio and knows only that customer, whose identity is given when the process starts. Its tools take no customer id. An order of another customer and an order that does not exist give the same `NOT_FOUND`.
- **The rule engine** (`src/rules/returns.py`) decides return and cancel eligibility without a model. The steps R0 to R13 run in a fixed order and the first step that decides wins. Flags and amounts are added afterwards and never change the decision. The window is 14 calendar days for a changed mind or a late delivery and 30 for a damaged or wrong item. A request above 500 BRL goes to a senior. The model only relays the result.
- **Writes** go to two tables only: `return_requests` and `escalation_tickets`, and the order server is the only one that inserts. `create_return_request` needs an approval token (`src/guardrails/approval.py`) that is made in code when the person clicks approve, is single-use and is bound to the order, the reason and the amount. The amount written must equal the refund the rules computed. Without the token the tool answers `APPROVAL_REQUIRED` and writes nothing.
- **The support representative's console** has no model. It lists the requests and tickets that need a person and changes their status in code, only from the state it showed.

## The operations side

- **The semantic layer** (`metrics.yaml`, `src/knowledge/semantic_layer.py`) defines 8 metrics and 5 dimensions. Each metric carries a caveat ("observational, not a cause") and every query binds the simulated today as a parameter. The Ops Data Agent tries the metric templates first.
- **Free SQL** is the fallback. The validator (`src/knowledge/sql_validator.py`, built on `sqlglot`) accepts a single `SELECT` or `WITH` statement over the safe views only, adds `LIMIT 1000` when it is missing and rejects `ATTACH` and `PRAGMA`. The runner (`src/knowledge/sql_runner.py`) opens the database read-only, with a timeout of 5 seconds for a query. The safe views (`src/knowledge/safe_views.py`) carry no ids, cities or review text. A failed query may be corrected twice. After that the answer says it could not be answered and shows the SQL that was tried.
- **Review themes** (`src/knowledge/review_themes.py`, `review_corpus.py`) are built from a sample of at most 50 reviews cut at 600 characters. A review with personal data is left out. A quote must be word for word a piece of a review in the sample, the frequency of a theme is counted by code, and a theme with no verified quote is rejected.
- **The critic** (`src/agents/critic.py`) checks that every number in an operations answer comes from a tool output, and may ask for one correction.

## The knowledge layer

The five policy documents are split into 28 sections, one section for each chunk. Each chunk is embedded as the document title, the section heading and the section, with `multilingual-e5-small` as quantized ONNX. Chroma is used through LlamaIndex and the index is in the repository (`policies/index/`). On 20 test questions the right section comes first for 14 and in the top three for 18. The policies are in Turkish only.

## What every model call passes

- **The outbound guard** (`src/guardrails/outbound.py`, `pii.py`, `guarded_llm.py`) masks personal data in everything that goes to the model, for the router and for every agent.
- **The limits** (`src/ui/call_budget.py`, `question_limit.py`) count model calls and questions for all visitors together, to keep the free quota for everyone.
- **Tracing** (`src/tracing.py`) records every run with OpenTelemetry and OpenInference, to Phoenix locally and to Langfuse for the demo, with an allowlist of attributes. Logs and traces carry keyed hashes instead of ids.

## Where things are

| Folder or file | What is in it |
|---|---|
| `src/orchestrator.py` | the router and the table of what each session may have |
| `src/rules/` | the rule engine (R0–R13) |
| `src/tools/` | plain Python tool functions: orders, eligibility, return requests, policies, escalation, review queue |
| `src/mcp_server/` | the order server and its client |
| `src/knowledge/` | embedding, policy index, semantic layer, safe views, SQL validator and runner, review corpus and themes |
| `src/guardrails/` | approval token, outbound guard, id hashing, write access |
| `src/agents/` | the three agents, the critic, the loop guard, the run log |
| `src/ui/` | chat session, session pool, limits, what the page shows |
| `config.py`, `metrics.yaml` | every setting, the semantic layer |
