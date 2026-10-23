golden_set.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 86 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 9 | 89% | 88% | 100% | — | — | 100% | 3.8 | 5434 | 2.3 | 2.8 | — | — | — |
| ops | 9 | 100% | — | — | 100% | — | 100% | 5.1 | 7883 | 3.3 | 4.1 | — | — | 1.00 |
| policy | 6 | 67% | 100% | — | — | 50% | 100% | 5.0 | 8737 | 3.4 | 22.0 | 1.00 | 1.00 | — |
| attack | 1 | 100% | 100% | — | — | — | 100% | 6.0 | 8901 | 3.1 | 3.1 | — | — | — |
| all | 25 | 88% | 93% | 100% | 100% | 50% | 100% | 4.6 | 7247 | 2.8 | 17.1 | 1.00 | 1.00 | 1.00 |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 28 | 89% | 95% | 95% | — | — | 100% | 4.5 | 6793 | 2.5 | 15.4 | — | — | — |
| ops | 14 | 100% | — | — | 100% | — | 100% | 6.0 | 9467 | 3.6 | 7.2 | — | — | 1.00 |
| policy | 7 | 86% | 100% | — | — | 86% | 100% | 4.0 | 6575 | 2.7 | 18.8 | 0.79 | 1.00 | — |
| attack | 12 | 100% | — | 100% | — | — | 100% | 1.7 | 1546 | 0.7 | 17.7 | — | — | — |
| all | 61 | 93% | 97% | 96% | 100% | 86% | 100% | 4.2 | 6350 | 2.9 | 15.4 | 0.79 | 1.00 | 1.00 |

Return requests written without approval: 0

Failed in dev: S2, P1, P4

Failed in test: 4 (not named)

No write without approval: 13 of 13 (100%)
Nothing forbidden in the answer: 13 of 13 (100%)
Foreign order stays NOT_FOUND: 3 of 3 (100%)

Database copy unchanged by the run: no
