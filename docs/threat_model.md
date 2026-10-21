# Threat model

This document says what an attacker could want from MarketDesk, where they can get in, what stops them today, and what the red teaming (milestone M4) still has to test. It is the plan for M4: every gap below names the task that tests or closes it, by its code in the plan (M4.1 is this document).

Written on 2026-10-20, from the code on the `test` branch at `8a8d426`; R15 and R16 updated the same day after the configuration review, R22 after the English attack run, R3 and R20 after the protocol layer review, R7 and R8 after the privacy fuzzing, R12 after the client layer measurement. Tests named below are in `tests/`. Lists used:

- **LLM:** OWASP Top 10 for LLM Applications 2025 (LLM01–LLM10).
- **ASI:** OWASP Top 10 for Agentic Applications 2026, official numbering of 2025-12-09 (ASI01–ASI10).
- **MCP:** OWASP MCP Top 10, 2025 beta (MCP01–MCP10).
- **ATLAS:** MITRE ATLAS techniques, checked against the published data file `ATLAS-2026.09.yaml` (release 2026.09, 2026-09-15) of `mitre-atlas/atlas-data`.

## 1. Scope

MarketDesk is a chat page with three session types. A **customer** asks about their own orders, returns and the policies; the Support Agent answers with four order tools on the project's own MCP server, a policy search and a hand-over to a person, and the only write (a return request) needs the person's click. An **operations** analyst asks for figures; the Ops Data Agent answers with metric templates or free SQL over safe views, read-only. A **support rep** decides on return requests and closes tickets; that session has no model. The session type is chosen with a button and the customer from a list of five demo customers; there is no sign-in.

The seven layers of the attack surface, as they apply here:

| Layer | What it is in MarketDesk |
|---|---|
| Client | The Streamlit page in the browser: what it draws from the model's text, and the messages a visitor can craft by hand |
| IDE | The coding assistants used to build the project; for the product, only the instruction files in the public repo |
| Protocol | The MCP connection between the Support Agent and the order server (stdio, one process per customer session) |
| Agent | The router, the two agents, their prompts, tools, loop limits and the approval flow |
| Application | The code around the agents: rule engine, SQL validator, safe views, outbound guard, session pool, rep console |
| Model | Gemini (`gemini-3.5-flash-lite`) behind the outbound guard; Groq as a switchable fallback |
| Server | The host: Streamlit Community Cloud for the demo, Docker Compose locally, SQLite files, the Chroma index, secrets, logs and traces, CI |

Out of scope: Gemini's and Streamlit's own infrastructure; attacks on the visitor's browser or network; the IDE layer beyond the instruction files (the product is not a coding tool). The page has no sign-in, so "who is the visitor" is not a control here; see R21.

## 2. Assets

| Asset | Why it matters | Where it lives |
|---|---|---|
| A1 Customer identity and orders | Seeing or acting on another customer's order is the main failure of a support agent | `customer_unique_id` in the order server's session; Olist tables in SQLite |
| A2 The write path: return requests and the approval token | A request written without the person's yes is money paid out on a model's word | `return_requests` table; token made and checked in the order server process |
| A3 Tickets and the rep's decisions | A misled rep approves the wrong request; a ticket is the one model text a person acts on | `escalation_tickets` table; rep console |
| A4 Raw data behind the operations view | Ids, cities, zip codes and review texts are not to leave the database | Raw Olist tables; only safe views are readable by free SQL |
| A5 Personal data sent to the model provider | Whatever is sent may be kept and used by the provider (free tier) | Outbound guard in front of every model call |
| A6 Logs and traces | A trace is a copy of the conversation; a hosted trace leaves the machine | Run logs, Phoenix locally, Langfuse for the demo |
| A7 System prompts and tool descriptions | Low value: the repo is public. Matters only if they held secrets | `src/agents/`, `src/orchestrator.py` |
| A8 Quota and money | The free daily quota is the demo's availability; the paid evaluation key spends money | Gemini free key (page and agents), paid key (evaluation only) |
| A9 Secrets | API keys and the id hash key | `.env` (gitignored), Streamlit secrets, GitHub secrets |
| A10 Integrity of answers | A wrong policy rule, amount or metric told with confidence | Rule engine, policy index, `metrics.yaml` |

## 3. Entry points

| # | Entry point | Who controls it | Reaches |
|---|---|---|---|
| E1 | Chat message | Any visitor | Router classifier, then the session's agent |
| E2 | Hand-crafted page messages (button clicks, widget values, a message sent past the closed chat box) | Any visitor | `app.py`, chat session, approval flow, rep console |
| E3 | Choice screen: session type, demo customer, page language | Any visitor | Which agent and order server start; F1, F8, F17 in `docs/security_review.md` |
| E4 | Policy sections returned by the search | Whoever can change `policies/` or the committed index | Support Agent's context |
| E5 | Data fields in tool results (order fields, statuses, metric rows) | The database; today only the loader writes the raw tables | Both agents' context |
| E6 | Ticket summaries | The model, steered by a customer | Rep console |
| E7 | MCP messages between the agent and the order server | Code on both sides; the model only picks a tool and its arguments | Order tools, the write connection |
| E8 | Dependencies, the embedding model, CI actions and images | Third parties | Everything at build or run time |
| E9 | Environment and secrets | The operator | Model calls, tracing, id hashes |

## 4. Risks

Status: **Holds** (a control in code and a test that shows it), **Partial** (a control, but a known way around it or no test of the attack), **Gap** (no control or no test), **Accepted** (known and left, with the reason).

| # | Layer | Risk | Lists | Control today | Shown by | Status | Task |
|---|---|---|---|---|---|---|---|
| R1 | Protocol, application | A customer reads or acts on another customer's order (BOLA), by claiming to be someone else or passing another id | LLM06; ASI03; MCP07; AML.T0051.000, AML.T0053 | Identity is set when the order server starts and is never a tool argument; a foreign, a missing and an unknown order answer the same `NOT_FOUND`; aliases mean nothing outside their session | `test_no_order_tool_takes_identity_or_an_approval_token`, `test_foreign_missing_and_unknown_alias_give_the_same_answer`, `test_alias_of_another_session_is_not_found`, `test_customer_cannot_open_a_request_for_a_foreign_order_even_with_a_token`; attack set A1, A2: 4 of 4; automated scan (DeepTeam, 2026-10-21, `eval/results/redteam_v1_*`): BOLA 3 of 3 (object access bypass, cross-customer access, unauthorized object manipulation) | Holds | M4.2 (done), M4.3 |
| R2 | Agent, application | A return request is written without the person's yes: the model, the customer or a fake note says "approved" | LLM06; ASI02, ASI09; AML.T0053, AML.T0048.000 | The token is made only by the approve click, in the order server process; it is random, used once and tied to order, reason and amount; the model has no approval tool | `test_model_saying_approved_is_not_an_approval`, `test_model_cannot_call_the_approval_tool`, `test_no_answer_ever_holds_the_approval_token`, `test_token_of_another_session_writes_nothing`, `test_amount_other_than_the_computed_one_is_refused`; attack set A3: 2 of 2; no write without approval in 16 of 16 attacks | Holds | M4.3 |
| R3 | Protocol, server | The order server's write connection can write every table, not only the two it needs | LLM06; ASI02, ASI03; MCP02; AML.T0101 | SQLite's authorizer on the server's connection: it reads anything and writes only new rows of `return_requests` and `escalation_tickets`; the rep console's connection may change only their status column (`src/guardrails/write_access.py`) | `test_the_server_connection_writes_nothing_but_new_requests_and_tickets`, `test_the_console_connection_may_change_only_the_status`, `tests/test_write_access.py` | Holds (fixed) | M4.11 (done) |
| R4 | Agent | Direct prompt injection and jailbreak: the customer or analyst tells the model to ignore its rules, play a role, or uses encodings (Base64, ROT13, leetspeak, another language) | LLM01; ASI01; MCP06; AML.T0051.000, AML.T0054, AML.T0068 | What matters is decided in code (rule engine, identity, token, tool binding per session); the router refuses a class the session may not have with a fixed text; prompt rule 9 says that text is data (a prompt is not a control) | `test_instruction_inside_the_message_does_not_pick_the_class`, `test_fooled_classifier_still_cannot_reach_the_ops_tools`, `test_claiming_to_be_the_operations_manager_changes_nothing`; attack set: 16 of 16 in Turkish; automated scan (DeepTeam, 2026-10-21, `eval/results/redteam_v1_*`): 37 of 37 judged attacks held, in seven forms (ROT-13 8, multilingual 8, permission escalation 6, Base64 4, prompt injection 4, roleplay 4, leetspeak 3), no write, no raw id | Holds for single messages: 16 hand-written and 37 generated attacks; several messages in M4.3 | M4.2 (done), M4.3 |
| R5 | Agent, application | Indirect injection through data: an instruction inside a policy section, a data field, a ticket summary or a review text | LLM01, LLM04, LLM08; ASI06; MCP06, MCP10; AML.T0051.001, AML.T0070, AML.T0066, AML.T0099 | Free SQL cannot read review texts (no view holds them); policies are five reviewed files and the index is built from them, and CI checks that the stored index holds exactly their texts; tools return chosen fields only; a ticket summary is read only by the rep queue, never by a model; prompt rule 9 and the policy tool's description say section text is information; the rule engine and the approval token decide whatever the text says | `test_review_text_cannot_be_read`, `test_outputs_hold_only_the_allowed_fields`, `test_stored_index_holds_exactly_the_policy_sections`, `test_free_sql_cannot_read_the_tickets`, `test_only_the_ticket_tool_the_server_and_the_rep_queue_name_the_tickets`; indirect injection set D1–D7b: 8 of 8 (planted section ranked first and not followed; instructions in item categories, a category name and a payment type not followed; no instruction in a ticket summary) | Holds for policies, data fields and tickets; reviews not tried (no review text reaches a model) | M4.4 (done) |
| R6 | Agent | A customer types the support agent's own note format, `[Note from the system: …]`, to pass as the system | ASI07; AML.T0051.000 | The outcome of a click is a record at the end of the model's instructions, which the customer cannot write into (with Gemini a system message mid-conversation would be merged into the customer's turn); a bracketed note typed by the customer is marked as theirs; the outcome itself is in the database and the card | `test_model_is_told_the_outcome_in_its_instructions`, `test_instructions_stay_as_written_until_something_happens_on_screen`, `test_a_system_note_typed_by_the_customer_is_marked_as_theirs`; attack set I3b; inter-agent set (security review, inter-agent messages): X2–X6, XF1, XF2 held, nothing written in 8 of 8 | Partial (fixed after a click): before any click a typed note still made the model claim a request that does not exist (X1); the record from the start is planned with the final run | M4.13 (done) |
| R7 | Model | Personal data reaches the model provider | LLM02; MCP10; AML.T0057 | Tools and safe views leave ids, cities and zip codes out; the outbound guard replaces raw ids (by aliases in a customer session), e-mails, phones and the session's known city and zip code in every message, including tool results and earlier tool arguments | `test_tool_that_leaks_on_purpose_does_not_reach_the_provider`, `test_without_the_guard_the_same_run_does_leak`, `test_nothing_personal_reaches_the_model_from_the_views`, `test_customer_classifier_masks_the_customers_own_city`, `test_only_the_guard_module_imports_a_provider` | Partial: matching is by shape, check digits and known values; measured with 35 hidden values, 12 caught at first, 27 after the fixes, 8 left as accepted limits (security review, privacy fuzzing; `tests/test_privacy_fuzz.py`) | M4.5 (done) |
| R8 | Server | Personal data or secrets in logs and traces | LLM02; MCP01, MCP08 | Run logs write the customer as a hash and no tool arguments; every span passes a masking exporter (keyed hashes, masks, secret values removed); a hosted target gets an allowlist of attributes, no message text, tool argument or error text | `test_run_is_logged_as_one_line_without_the_customer_id`, `test_trace_of_a_run_holds_no_raw_id_city_or_zip`, `test_no_secret_is_in_any_span`, `test_hosted_target_gets_no_message_text`, `test_hosted_target_gets_no_event_detail_or_error_text` | Partial: the trace scrubber and the ticket summary pass the same guard as R7 (27 of 35; the summary caught 2 before it did) | M4.5 (done) |
| R9 | Application | SQL injection and data theft through the operations agent: writes, ATTACH, PRAGMA, raw tables, review texts | LLM05; ASI05; MCP05; AML.T0053, AML.T0086, AML.T0101 | Validator on a real parser (one SELECT, forbidden nodes anywhere in the tree, views only, no unknown functions, row limit); read-only connection; ATTACH limit 0; 5-second timeout; at most 2 corrections | `test_attack_is_refused_and_the_database_is_unchanged`, `test_write_hidden_in_a_cte_is_refused`, `test_connection_refuses_attach_and_creates_no_file`, `test_function_used_as_a_table_is_refused`, `test_cte_may_not_take_the_name_of_something_real`; attack set A4: 3 of 3, I7c; automated scan (DeepTeam, 2026-10-21, `eval/results/redteam_v1_*`): SQL injection 3 of 3 (blind, union based, error based), reconnaissance 3 of 3 (file metadata, database schema, retrieval configuration) | Holds | M4.2 (done) |
| R10 | Agent, application | A session reaches another session type's tools (BFLA, RBAC): a customer asks for figures, an analyst for a customer's orders, a crafted click from another session | LLM06; ASI03; MCP07 | The session type is set by the start button; each agent has only its own tools; the rep queue is made only for the rep identity | `test_ops_session_is_never_offered_customer_tools`, `test_session_type_stays_what_it_was_at_sign_in`, `test_a_rep_button_sent_from_another_session_changes_nothing`, `test_a_click_on_a_start_button_that_is_gone_keeps_the_session`; attack set A7a; automated scan (DeepTeam, 2026-10-21, `eval/results/redteam_v1_*`): BFLA 3 of 3, RBAC 3 of 3, excessive agency 3 of 3 | Holds | M4.2 (done) |
| R11 | Agent | The system prompt is revealed | LLM07; AML.T0056, AML.T0069.002 | The prompts hold no secret, no identity and no data; they are in the public repo anyway. The model is told not to reveal them | Attack set I7b; automated scan (DeepTeam, 2026-10-21, `eval/results/redteam_v1_*`): prompt leakage 7 of 7 judged (one operations case was not sent: the attacker could not write it) | Accepted: nothing to protect; no secret or personal data came out | M4.2 (done) |
| R12 | Client | The page draws what the model wrote: a markdown image that calls another site, HTML, a script, a `javascript:` link, in an answer, a ticket summary, the "how computed" line or the SQL window | LLM05; AML.T0067 | Images replaced and links made plain in answers, in the visitor's own messages and in the "how computed" line; ticket summaries are plain text; the SQL window is code; Streamlit draws no raw HTML | `test_every_form_of_link_loses_its_target`, `test_a_link_in_the_model_answer_cannot_be_clicked`, `test_a_link_or_image_the_visitor_types_is_drawn_inert`, `test_an_image_in_the_model_answer_reaches_no_other_site`, `test_a_ticket_summary_is_plain_text_and_the_ticket_can_be_closed`; browser measurement in security review F2 | Holds: the page draws markup inert (18 forms, five paths, measured in Chrome); live, the model wrote none in 8 tries (3 reached an agent) | M4.10 (done) |
| R13 | Agent, application | Wrong facts told with confidence: a made-up policy section, metric or period, a false premise accepted, a causal claim | LLM09; AML.T0062 | Eligibility comes from the rule engine; policy answers cite their section and say when the policy does not cover a topic; metric answers carry their SQL and caveat, added by code; the evaluation scores faithfulness and causal claims | `test_eligibility_comes_from_the_rule_engine`, `test_document_says_what_it_does_not_cover`, `test_metric_answer_carries_its_sql_and_caveat`; golden set (final report); misinformation set M1–M14 (security review, misinformation; `eval/results/misinformation_v1_*`): 12 of 14, no citation the search did not return, no number missing from the tool output, no date after the simulated today (checks in code: `test_citations_are_read_in_both_languages`, `test_numbers_from_the_tool_pass_however_they_are_written`); the two failures are router over-refusals, not wrong facts | Holds for the 14 tried cases; what a policy answer says beyond its citations is scored only by the judge | M4.7 (done) |
| R14 | Agent, server | Unbounded consumption: tool loops, heavy SQL, long messages, many sessions, the free daily quota used up for everyone | LLM10; ASI08; AML.T0034, AML.T0034.002, AML.T0029 | 8 steps a message; the same call at most twice; 12 tool calls a message; 2 SQL corrections; 1,000 characters a message; 60 questions an hour and 400 model calls a day for all visitors; 10 open sessions, idle ones closed after 15 minutes; SQL timeout 5 s and 1,000 rows | `test_run_stops_at_the_step_limit`, `test_third_identical_call_is_not_run`, `test_calls_past_the_tool_limit_of_a_message_are_not_run`, `test_a_message_over_the_limit_never_reaches_the_model`, `test_the_call_budget_counts_every_model_call`, `test_visitors_asking_at_once_do_not_pass_the_limit_together`, `test_no_new_session_while_the_pool_is_full`, `test_query_that_runs_too_long_is_stopped`, `test_clicks_on_the_card_use_no_model_call_and_write_once` | Holds (fixed): measured scenario by scenario (security review, unbounded consumption); one visitor can still hold the sessions or the day's budget for everyone (accepted for a demo) | M4.6 (done) |
| R15 | Server | Supply chain: a compromised or vulnerable dependency, model file, CI action or image | LLM03; ASI04; MCP04; AML.T0010.001, AML.T0010.003 | All dependencies pinned with `==` in `uv.lock`; `task audit` in CI weekly and on lock changes, five unreachable advisories explained (F16); actions pinned to commit hashes; CI runners pinned to `ubuntu-24.04`; Compose images pinned by digest; embedding model pinned to a revision; Streamlit and Compose settings reviewed | Security review F16, F18; `test_only_the_guard_module_imports_a_provider`, `test_the_page_sends_no_usage_statistics` | Holds; the hosting platform's own image is not ours to pin | M4.8 |
| R16 | Server | Secrets leak: in the repo history, logs, spans, screenshots, or the paid key used by the page | MCP01; AML.T0055 | `.env` gitignored; whole history scanned for every `.env` value and key patterns, 0 hits (2026-10-20); secret values removed from spans; the order server process gets only its four variables and six basic ones from the MCP SDK, no API key; the paid key is read only for evaluation runs started with `--paid` | `test_no_secret_is_in_any_span`, `test_the_page_and_the_agents_never_ask_for_the_paid_key`, `test_paid_uses_the_paid_key`; security review F18 (no instruction or secret file in the repo) | Holds | M4.8 (done) |
| R17 | Agent, client | Human-agent trust: the model's text contradicts the approval card ("approve and you get 1,000 BRL"), calls an order eligible against the rules, or a ticket summary pushes the rep | ASI09; AML.T0130, AML.T0048.000 | The card is drawn from the order server's pending request, not from the model's text; the rep decides on amount, reason and status from the database; the console says summaries are written by the model; the evaluation checks the answer's amounts against the card and tools and its yes against the rule engine's no | `test_a_message_through_the_closed_chat_box_leaves_the_approval_as_shown`, `test_pending_request_is_described_with_an_alias`, `test_a_later_turn_is_held_to_the_decision_of_an_earlier_one`; human trust set H1–HF3 (security review, human-agent trust): 7 of 8; security review F5, F14 | Partial: no wrong amount, exception or pushed summary; the text said a damaged item's freight is not refunded (H2, from the field `freight_refund`), fixed with the final run | M4.12 (done) |
| R18 | Agent, protocol | Cascading failures: a 503 or a tool error in the middle of an approval, a fake tool answer, a routing trick that sends a message to the wrong agent | ASI07, ASI08 | Approval and write are one call inside the order server; a failed write is reported, not retried by the model; a request the person never saw is dropped when its message fails; a fooled router still reaches only the session's own agent; the rule engine decides whatever a typed tool answer says | `tests/test_cascading_failures.py` (a card shown before a failure, a request never shown, a failure after the click), `test_approval_that_fails_is_reported`, `test_fooled_classifier_still_cannot_reach_the_ops_tools`; inter-agent set X3–X6 | Holds (fixed): a request left waiting by a failed message used to come up with the next one; failures injected with the stand-in model only, a real 503 cannot be forced live | M4.13 (done) |
| R19 | Server | Audit and rogue behaviour: an attack that leaves no trace, a rep decision nobody can follow, an unexpected tool call nobody sees, no quick way to stop a session or the page | MCP08; ASI10 | One log line per run (steps, tokens, tools, customer hash); spans with the rule decision, the SQL check and the approval answer; decisions stay in the database with their status | `test_every_run_is_logged_with_steps_and_tokens`, `test_rule_decision_is_on_the_tool_span`, `test_approval_and_decline_are_spans_of_their_own`, `test_sql_check_is_on_the_tool_span` | Gap: no check that each attack is visible; no alert; no written way to stop a session or the page | M4.14 |
| R20 | Protocol | Tool poisoning, shadow or look-alike MCP servers, command injection through the server launch | MCP03, MCP05, MCP09; AML.T0010.005, AML.T0110 | One own server, started with the same interpreter and a fixed module name; tool descriptions are the docstrings in the repo; no third-party MCP server, no shell, no tool that runs code | `test_descriptions_are_the_docstrings_of_the_wrapped_functions`, `test_server_offers_the_model_tools_and_the_control_tools`, `test_control_tools_of_the_server_are_not_given_to_the_model` | Holds; checked item by item in the security review (MCP section) | M4.11 (done) |
| R21 | Client, server | Shared demo state: without sign-in any visitor may open any session type and pick any demo customer, and sees what the last visitor opened | ASI03; MCP07 | Demo customers are a public dataset with no personal data; operations reads only the safe views; the rep sees hashes only; the README says the data is shared | Security review F6, F7 | Accepted for a demo | none |
| R22 | Agent | The English sessions resist attacks less well than the Turkish ones | LLM01; ASI01; AML.T0051.000 | Same code controls in both languages (F17); prompts tell the model to answer in the session's language | English attack set: 16 of 16, 36 of 36 checks held, no write without approval, the same as in Turkish (final report, section English); automated scan (DeepTeam, 2026-10-21, `eval/results/redteam_v1_*`): 8 multilingual attacks on Turkish sessions held; the scan did not run on English sessions | Holds for the hand-written set in both languages and for multilingual attacks on Turkish sessions | M4.2 (done) |

## 5. Coverage of the three lists

"Applies" means the risk exists in this system; the risks column links the rows above.

### OWASP Top 10 for LLM Applications 2025

| Item | Applies | Why | Risks |
|---|---|---|---|
| LLM01 Prompt Injection | Yes | Every message and every tool result reaches a model | R4, R5, R6, R22 |
| LLM02 Sensitive Information Disclosure | Yes | Orders hold ids, cities and zip codes; the provider and the traces are outside the process | R7, R8 |
| LLM03 Supply Chain | Yes | Python dependencies, an embedding model from Hugging Face, CI actions and images | R15 |
| LLM04 Data and Model Poisoning | Partly | No training or fine-tuning; poisoning applies to the policy index and the data the tools read | R5 |
| LLM05 Improper Output Handling | Yes | Model text is drawn in the browser; model-written SQL is run | R9, R12 |
| LLM06 Excessive Agency | Yes | The Support Agent has a write tool; the order server's connection can write more than it needs | R1, R2, R3, R10 |
| LLM07 System Prompt Leakage | Yes, low | The prompts are public in the repo and hold nothing secret | R11 |
| LLM08 Vector and Embedding Weaknesses | Partly | One local index of five public policy documents, no user content in it, no tenants; the risk is a changed index | R5 |
| LLM09 Misinformation | Yes | Policy answers and figures are told to customers and analysts | R13 |
| LLM10 Unbounded Consumption | Yes | Free daily quota shared by all visitors; agent loops; heavy SQL | R14 |

### OWASP Top 10 for Agentic Applications 2026

| Item | Applies | Why | Risks |
|---|---|---|---|
| ASI01 Agent Goal Hijack | Yes | A message or a data field could turn the agent to another goal | R4, R22 |
| ASI02 Tool Misuse and Exploitation | Yes | Tools are called with arguments the model writes | R2, R3 |
| ASI03 Identity and Privilege Abuse | Yes | Three session types with different rights; the order server acts for one customer | R1, R3, R10, R21 |
| ASI04 Agentic Supply Chain Vulnerabilities | Yes | Agent framework, MCP SDK and model provider are third-party | R15 |
| ASI05 Unexpected Code Execution | Partly | No tool runs code or shell; the one code-like output is SQL, which is checked and run read-only | R9 |
| ASI06 Memory and Context Poisoning | Partly | No memory across sessions; within a session the conversation and the retrieved sections are the context | R5 |
| ASI07 Insecure Inter-Agent Communication | Partly | Two agents never talk to each other; the router hands a message to one agent, and the code tells the support agent what happened on screen in its instructions | R6, R18 |
| ASI08 Cascading Failures | Yes | A failure in the model, the order server or the database in the middle of a flow | R14, R18 |
| ASI09 Human-Agent Trust Exploitation | Yes | The customer approves a card next to model text; the rep reads model-written summaries | R2, R17 |
| ASI10 Rogue Agents | Partly | Agents have few tools and fixed limits; what is missing is noticing and stopping misbehaviour | R19 |

### OWASP MCP Top 10 (2025, beta)

| Item | Applies | Why | Risks |
|---|---|---|---|
| MCP01 Token Mismanagement and Secret Exposure | Partly | The order server holds no API key; the approval token lives and dies in it; the id hash key is passed to it | R8, R16 |
| MCP02 Privilege Escalation via Scope Creep | Yes | The server's database connection could write every table; now limited to new rows of its two tables | R3 |
| MCP03 Tool Poisoning | Low | Own server, own tool descriptions in the repo; no third-party server | R20 |
| MCP04 Software Supply Chain Attacks and Dependency Tampering | Yes | The MCP SDK and its dependencies | R15 |
| MCP05 Command Injection and Execution | Low | The server runs no shell; it is launched with a fixed module name | R9, R20 |
| MCP06 Prompt Injection via Contextual Payloads | Yes | Tool results go back into the model's context | R4, R5 |
| MCP07 Insufficient Authentication and Authorization | Yes | The client and server are the same application over stdio; authorization is the session the server was started with | R1, R10, R21 |
| MCP08 Lack of Audit and Telemetry | Yes | Tool calls must be visible after an attack | R8, R19 |
| MCP09 Shadow MCP Servers | No | One server, started by the application; no discovery or remote servers | R20 |
| MCP10 Context Injection and Over-Sharing | Yes | Tool results carry data into the model's context and on to the provider | R5, R7 |

### The seven layers

| Layer | Risks |
|---|---|
| Client | R12, R17, R21 |
| IDE | Instruction files in the public repo (`CLAUDE.md` is gitignored; checked in M4.8); no product risk |
| Protocol | R1, R3, R18, R20 |
| Agent | R2, R4, R5, R6, R10, R11, R13, R14, R17, R18, R22 |
| Application | R1, R2, R5, R9, R10, R13 |
| Model | R7 |
| Server | R3, R8, R14, R15, R16, R19, R21 |

## 6. Gaps, in order

1. **R19: audit and stopping** (M4.14).
2. **R6 before any click** (final run): a typed system note can still make the model claim a request that does not exist; nothing is written.
3. **R17 freight next to the card** (final run): the eligibility answer does not say whether the freight is part of the refund, and the model can say it is not.

Multi-turn attacks on approval and identity (M4.3) cover R1 and R2 over several messages, which the single-message attack set does not.

## 7. Budget

Gemini requests on the free key, per M4 task (estimates from the task list; 500 a day, shared with the page):

| Task | Risks | Gemini requests |
|---|---|---|
| M4.1 Threat model (this document) | all | 0 |
| M4.2 Automated scan | R1, R4, R9, R10, R11, R22 | ~100 for the system; attacker and judge off Gemini |
| M4.3 Multi-turn attacks | R1, R2 | ~60 |
| M4.4 Indirect injection and poisoning | R5 | ~30 |
| M4.5 Privacy fuzzing | R7, R8 | 0 |
| M4.6 Unbounded consumption | R14 | little |
| M4.7 Misinformation | R13 | ~50 |
| M4.8 Supply chain and configuration | R15, R16 | 0 |
| M4.9 Red team report | all | 0 |
| M4.10 Client layer | R12 | ~20 |
| M4.11 Protocol layer | R3, R20 | 0 |
| M4.12 Human-agent trust | R17 | ~40 |
| M4.13 Inter-agent and cascading | R6, R18 | ~30 |
| M4.14 Audit and rogue agents | R19 | 0 |
| **Total** | | **~330** |

- The attacker and the judge of the automated scan do not use the Gemini quota: Groq or a local model through Ollama, decided when M4.2 starts (2026-10-23).
- Every run uses the evaluation cache; a rerun of the same attacks costs nothing.
- The paid evaluation key (500 TRY cap on the Gemini API, 600 live calls a run) is used only in runs the author starts with `--paid`; the page and the agents never use it.
- Attacks that write run on a copy of the database, never on the demo database.
