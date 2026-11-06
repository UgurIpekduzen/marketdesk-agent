# Final evaluation: gemini `gemini-3.5-flash-lite`, temperature 0

## Baselines and the system

| System · group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Faithful | Helpful | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 · support | 37 | 14% | — | — | — | — | — | — | 1.0 | 3281 | 1.0 | 1.6 |
| B0 · policy | 13 | 100% | — | — | — | 100% | 0.92 | 1.00 | 1.0 | 3274 | 0.9 | 1.2 |
| B1 · policy | 13 | 92% | — | — | — | 91% | 0.92 | 0.88 | 1.0 | 751 | 0.8 | 1.1 |
| B2 · ops | 21 | 33% | — | — | 33% | — | — | — | 1.0 | 690 | 0.9 | 1.4 |
| Final · support | 37 | 89% | 97% | 100% | — | — | — | — | 4.2 | 6752 | 2.2 | 3.6 |
| Final · policy | 13 | 100% | 100% | — | — | 100% | 0.95 | 1.00 | 4.5 | 8247 | 2.5 | 4.0 |
| Final · ops | 23 | 100% | — | — | 100% | — | — | — | 6.0 | 10024 | 2.6 | 3.3 |
| Final · attack | 13 | 100% | 100% | 100% | — | — | — | — | 2.2 | 2533 | 0.8 | 3.4 |
| Final · all | 86 | 95% | 98% | 100% | 100% | 100% | 0.95 | 1.00 | 4.4 | 7215 | 2.4 | 3.6 |

## Targets

| Target | At least | Measured | |
|---|---|---|---|
| Task success | 80% | 95% | met |
| Tool-call accuracy | 90% | 98% | met |
| Decision accuracy | 100% | 100% | met |
| SQL execution accuracy | 75% | 100% | met |
| Policy faithfulness | 0.85 | 0.95 | met |
| No write without approval | 100% | 100% (16 of 16) | met |
| Nothing forbidden in the answer | 95% | 100% (16 of 16) | met |
| Foreign order stays NOT_FOUND | 100% | 100% (4 of 4) | met |

## Three numbers

- Improvement over the baseline: the semantic layer adds 67 points of SQL execution accuracy (Final minus B2).
- Security tests: 36 of 36 attack checks held (100%). 9 more sets of the red teaming: 126 of 126 examples passed, 0 return requests written without approval.
- Cost and latency of one task: 4.4 steps, 7215 tokens, p50 2.4 s, p95 3.6 s of model time; cost about 0.00241 USD at the list price of 2026-10-14 (0 on the free tier used).

## Attack sets

| Set | Examples | Passed | Written without approval |
|---|---|---|---|
| Indirect injection | 8 | 8 | 0 |
| Review insight and review attacks | 14 | 14 | 0 |
| Client layer | 8 | 8 | 0 |
| Misinformation | 14 | 14 | 0 |
| Inter-agent messages | 8 | 8 | 0 |
| Human-agent trust | 8 | 8 | 0 |
| Attacks made from templates | 28 | 28 | 0 |
| Attacks made from templates, in English | 30 | 30 | 0 |
| Attacks over several messages | 8 | 8 | 0 |
| **All** | 126 | 126 | 0 |

## The critic of the operations agent

| Set | Critic | Examples | Task success | Answers with a number no tool returned | Corrected | Flagged | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|
| Number traps | on | 6 | 100% | 0 | 3 | 0 | 9.2 | 17484 | 4.1 | 5.4 |
| Number traps | on, plain | 6 | 100% | 0 | 3 | 0 | 9.2 | 17503 | 4.2 | 6.2 |
| Number traps | off | 6 | 50% | 3 | 0 | 0 | 7.3 | 12476 | 2.8 | 4.2 |
| Golden set | on | 23 | 100% | 0 | 1 | 0 | 6.0 | 10024 | 2.6 | 3.3 |
| Golden set | on, plain | 23 | 100% | 1 | 0 | 1 | 6.0 | 9825 | 2.6 | 3.3 |
| Golden set | off | 23 | 100% | 1 | 0 | 0 | 5.8 | 9438 | 2.6 | 3.2 |
| Misinformation | on | 7 | 100% | 0 | 1 | 0 | 5.0 | 8168 | 2.6 | 4.0 |
| Misinformation | on, plain | 7 | 100% | 0 | 1 | 0 | 4.7 | 7531 | 2.6 | 3.7 |
| Misinformation | off | 7 | 86% | 1 | 0 | 0 | 4.0 | 6088 | 2.3 | 2.6 |

The critic checks in code that every number in an answer is one a tool returned; on a miss the model is asked once more, and an answer that still holds one is shown with a note. "on" asks for the correction in the wording in use, which also tells the model to compute a derived value with a query; "on, plain" is the first wording, which only asks for the tools' numbers. Only operations answers are counted. Numbers in the right amount on the wrong thing are not seen by it.

## Multi-turn conversations

| Split | n | Task success | Tool-call accuracy | Decision | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|
| dev | 4 | 100% | 100% | 100% | 9.5 | 15753 | 4.1 | 5.6 |
| test | 12 | 100% | 100% | 100% | 7.0 | 11454 | 2.7 | 4.6 |

- Each example is one conversation: messages, and the approve or decline click made in code as the page makes it. An example passes only if every turn does.
- Requests as expected after the clicks and at the end: 16 of 16.
- Return requests written by a message rather than an approve click: 0.
- Passed per flow, dev only: M1 1 of 1, M3 1 of 1, M6 1 of 1, M8 1 of 1. The test split is given as totals only: its three variants of a flow test one case, so a count per flow would name the case.

## English

| Group | n | Task success TR | Task success EN | Decision TR | Decision EN | SQL execution TR | SQL execution EN | Source TR | Source EN | Faithful TR | Faithful EN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 37 | 89% | 95% | 100% | 100% | — | — | — | — | — | — |
| policy | 13 | 100% | 77% | — | — | — | — | 100% | 91% | 0.95 | 0.86 |
| ops | 23 | 100% | 91% | — | — | 100% | 90% | — | — | — | — |
| attack | 13 | 100% | 100% | 100% | 100% | — | — | — | — | — | — |
| all | 86 | 95% | 92% | 100% | 100% | 100% | 90% | 100% | 91% | 0.95 | 0.86 |

- The same 86 examples and 16 attacks, asked in English in English sessions, with the same expectations; only the questions and the texts an answer must or must not hold were translated.
- Golden set in English: dev 23 of 25, test 56 of 61 examples passed. The test split stays held out in English too.
- Attack checks in English: 36 of 36 held (100%).
- Return requests written without approval in English: 0.
- The policy documents are Turkish: an English answer is judged against the Turkish text. The judge's English scores were not checked by hand.

## How to read this

- Golden set: dev 24 of 25, test 58 of 61 examples passed. Only the test split was held out while the system was worked on.
- Faithfulness and helpfulness are scored by a judge model (`gemini-3.5-flash-lite`), the other numbers by rules without a model.
- A person checked 12 of the judge's scores by hand and agreed with 11 (92%); see the judge check sheet in this folder.
- Return requests written without approval: 0. Database copy unchanged by the attack run: yes.
- B0 is one model call with the full policy text, B1 with the five closest sections, B2 writes SQL from the raw schema. A baseline's task success is its own rule; see the baselines results file.
