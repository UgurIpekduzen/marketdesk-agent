# Final evaluation: gemini `gemini-3.5-flash-lite`, temperature 0

## Baselines and the system

| System · group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Faithful | Helpful | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 · support | 37 | 14% | — | — | — | — | — | — | 1.0 | 3281 | 1.0 | 1.6 |
| B0 · policy | 13 | 100% | — | — | — | 100% | 0.92 | 1.00 | 1.0 | 3274 | 0.9 | 1.2 |
| B1 · policy | 13 | 92% | — | — | — | 91% | 0.92 | 0.88 | 1.0 | 751 | 0.8 | 1.1 |
| B2 · ops | 21 | 33% | — | — | 33% | — | — | — | 1.0 | 690 | 0.9 | 1.4 |
| Final · support | 37 | 89% | 93% | 97% | — | — | — | — | 4.3 | 6463 | 2.5 | 15.4 |
| Final · policy | 13 | 77% | 100% | — | — | 73% | 0.88 | 1.00 | 4.5 | 7573 | 2.9 | 22.0 |
| Final · ops | 23 | 100% | — | — | 100% | — | — | — | 5.7 | 8847 | 3.5 | 4.6 |
| Final · attack | 13 | 100% | 100% | 100% | — | — | — | — | 2.0 | 2112 | 0.8 | 17.7 |
| Final · all | 86 | 92% | 95% | 97% | 100% | 73% | 0.88 | 1.00 | 4.3 | 6611 | 2.8 | 17.1 |

## Targets

| Target | At least | Measured | |
|---|---|---|---|
| Task success | 80% | 92% | met |
| Tool-call accuracy | 90% | 95% | met |
| Decision accuracy | 100% | 97% | NOT met |
| SQL execution accuracy | 75% | 100% | met |
| Policy faithfulness | 0.85 | 0.88 | met |
| No write without approval | 100% | 100% (16 of 16) | met |
| Nothing forbidden in the answer | 95% | 100% (16 of 16) | met |
| Foreign order stays NOT_FOUND | 100% | 100% (4 of 4) | met |

## Three numbers

- Improvement over the baseline: the semantic layer adds 67 points of SQL execution accuracy (Final minus B2).
- Security tests: 36 of 36 attack checks held (100%). 6 more sets of the red teaming: 50 of 54 examples passed, 0 return requests written without approval.
- Cost and latency of one task: 4.3 steps, 6611 tokens, p50 2.8 s, p95 17.1 s of model time; cost about 0.00221 USD at the list price of 2026-10-14 (0 on the free tier used).

## Attack sets

| Set | Examples | Passed | Written without approval |
|---|---|---|---|
| Indirect injection | 8 | 8 | 0 |
| Client layer | 8 | 8 | 0 |
| Misinformation | 14 | 12 | 0 |
| Inter-agent messages | 8 | 7 | 0 |
| Human-agent trust | 8 | 7 | 0 |
| Attacks over several messages | 8 | 8 | 0 |
| **All** | 54 | 50 | 0 |

## Multi-turn conversations

| Split | n | Task success | Tool-call accuracy | Decision | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|
| dev | 4 | 100% | 100% | 100% | 9.0 | 13808 | 5.9 | 12.8 |
| test | 12 | 83% | 90% | 83% | 7.2 | 10833 | 4.3 | 13.3 |

- Each example is one conversation: messages, and the approve or decline click made in code as the page makes it. An example passes only if every turn does.
- Requests as expected after the clicks and at the end: 16 of 16.
- Return requests written by a message rather than an approve click: 0.
- Passed per flow, dev only: M1 1 of 1, M3 1 of 1, M6 1 of 1, M8 1 of 1. The test split is given as totals only: its three variants of a flow test one case, so a count per flow would name the case.

## English

| Group | n | Task success TR | Task success EN | Decision TR | Decision EN | SQL execution TR | SQL execution EN | Source TR | Source EN | Faithful TR | Faithful EN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 37 | 89% | 86% | 97% | 100% | — | — | — | — | — | — |
| policy | 13 | 77% | 92% | — | — | — | — | 73% | 91% | 0.88 | 0.87 |
| ops | 23 | 100% | 96% | — | — | 100% | 95% | — | — | — | — |
| attack | 13 | 100% | 100% | 100% | 100% | — | — | — | — | — | — |
| all | 86 | 92% | 92% | 97% | 100% | 100% | 95% | 73% | 91% | 0.88 | 0.87 |

- The same 86 examples and 16 attacks, asked in English in English sessions, with the same expectations; only the questions and the texts an answer must or must not hold were translated.
- Golden set in English: dev 22 of 25, test 57 of 61 examples passed. The test split stays held out in English too.
- Attack checks in English: 36 of 36 held (100%).
- Return requests written without approval in English: 0.
- The policy documents are Turkish: an English answer is judged against the Turkish text. The judge's English scores were not checked by hand.

## How to read this

- Golden set: dev 22 of 25, test 57 of 61 examples passed. Only the test split was held out while the system was worked on.
- Faithfulness and helpfulness are scored by a judge model (`gemini-3.5-flash-lite`), the other numbers by rules without a model.
- A person checked 12 of the judge's scores by hand and agreed with 11 (92%); see the judge check sheet in this folder.
- Return requests written without approval: 0. Database copy unchanged by the attack run: yes.
- B0 is one model call with the full policy text, B1 with the five closest sections, B2 writes SQL from the raw schema. A baseline's task success is its own rule; see the baselines results file.
