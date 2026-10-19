# Final evaluation: gemini `gemini-3.5-flash-lite`, temperature 0

## Baselines and the system

| System · group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Faithful | Helpful | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 · support | 37 | 14% | — | — | — | — | — | — | 1.0 | 3281 | 1.0 | 1.6 |
| B0 · policy | 13 | 100% | — | — | — | 100% | 0.92 | 1.00 | 1.0 | 3274 | 0.9 | 1.2 |
| B1 · policy | 13 | 92% | — | — | — | 91% | 0.92 | 0.88 | 1.0 | 751 | 0.8 | 1.1 |
| B2 · ops | 19 | 37% | — | — | 37% | — | — | — | 1.0 | 684 | 0.9 | 1.4 |
| Final · support | 37 | 97% | 97% | 100% | — | — | — | — | 4.2 | 5434 | 2.4 | 19.6 |
| Final · policy | 13 | 92% | 100% | — | — | 91% | 0.95 | 1.00 | 4.6 | 7187 | 2.9 | 46.3 |
| Final · ops | 21 | 95% | — | — | 95% | — | — | — | 6.4 | 8794 | 2.9 | 5.5 |
| Final · attack | 13 | 100% | 100% | 100% | — | — | — | — | 2.0 | 1856 | 0.8 | 32.6 |
| Final · all | 84 | 96% | 98% | 100% | 95% | 91% | 0.95 | 1.00 | 4.5 | 5992 | 2.7 | 19.6 |

## Targets

| Target | At least | Measured | |
|---|---|---|---|
| Task success | 80% | 96% | met |
| Tool-call accuracy | 90% | 98% | met |
| Decision accuracy | 100% | 100% | met |
| SQL execution accuracy | 75% | 95% | met |
| Policy faithfulness | 0.85 | 0.95 | met |
| No write without approval | 100% | 100% (16 of 16) | met |
| Nothing forbidden in the answer | 95% | 100% (16 of 16) | met |
| Foreign order stays NOT_FOUND | 100% | 100% (4 of 4) | met |

## Three numbers

- Improvement over the baseline: the semantic layer adds 58 points of SQL execution accuracy (Final minus B2).
- Security tests: 36 of 36 attack checks held (100%).
- Cost and latency of one task: 4.5 steps, 5992 tokens, p50 2.7 s, p95 19.6 s of model time; cost about 0.00202 USD at the list price of 2026-10-14 (0 on the free tier used).

## How to read this

- Golden set: dev 20 of 23, test 61 of 61 examples passed. Only the test split was held out while the system was worked on.
- Faithfulness and helpfulness are scored by a judge model (`gemini-3.5-flash-lite`), the other numbers by rules without a model.
- A person checked 12 of the judge's scores by hand and agreed with 11 (92%); see the judge check sheet in this folder.
- Return requests written without approval: 0. Database copy unchanged by the attack run: yes.
- B0 is one model call with the full policy text, B1 with the five closest sections, B2 writes SQL from the raw schema. A baseline's task success is its own rule; see the baselines results file.
