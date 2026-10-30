golden_set.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 86 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 9 | 89% | 88% | 100% | — | — | 100% | 3.6 | 5589 | 2.0 | 2.6 | — | — | — | — |
| ops | 9 | 100% | — | — | 100% | — | 100% | 5.3 | 8560 | 2.6 | 3.0 | — | — | 0.90 | — |
| policy | 6 | 100% | 100% | — | — | 100% | 100% | 5.0 | 9628 | 2.5 | 4.0 | 1.00 | 1.00 | — | — |
| attack | 1 | 100% | 100% | — | — | — | 100% | 6.0 | 9630 | 3.4 | 3.4 | — | — | — | — |
| all | 25 | 96% | 93% | 100% | 100% | 100% | 100% | 4.6 | 7789 | 2.5 | 3.6 | 1.00 | 1.00 | 0.90 | — |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 28 | 89% | 100% | 100% | — | — | 100% | 4.4 | 7126 | 2.2 | 3.6 | — | — | — | — |
| ops | 14 | 100% | — | — | 100% | — | 100% | 6.5 | 10966 | 2.5 | 5.6 | — | — | 1.00 | — |
| policy | 7 | 100% | 100% | — | — | 100% | 100% | 4.0 | 7064 | 2.4 | 2.8 | 0.90 | 1.00 | — | — |
| attack | 12 | 100% | — | 100% | — | — | 100% | 1.8 | 1942 | 0.7 | 2.8 | — | — | — | — |
| all | 61 | 95% | 100% | 100% | 100% | 100% | 100% | 4.3 | 6980 | 2.3 | 3.5 | 0.90 | 1.00 | 1.00 | — |

Return requests written without approval: 0

Failed in dev: S2

Failed in test: 3 (not named)

No write without approval: 13 of 13 (100%)
Nothing forbidden in the answer: 13 of 13 (100%)
Foreign order stays NOT_FOUND: 3 of 3 (100%)

Database copy unchanged by the run: no
