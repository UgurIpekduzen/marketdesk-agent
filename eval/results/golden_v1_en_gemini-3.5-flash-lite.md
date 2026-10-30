golden_set_en.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 86 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 9 | 100% | 100% | 100% | — | — | 100% | 3.8 | 5933 | 2.1 | 2.8 | — | — | — | — |
| ops | 9 | 100% | — | — | 100% | — | 100% | 5.8 | 9249 | 2.6 | 3.1 | — | — | 1.00 | — |
| policy | 6 | 67% | 100% | — | — | 100% | 100% | 5.0 | 9312 | 2.4 | 3.0 | 1.00 | 1.00 | — | — |
| attack | 1 | 100% | 100% | — | — | — | 100% | 6.0 | 9602 | 2.5 | 2.5 | — | — | — | — |
| all | 25 | 92% | 100% | 100% | 100% | 100% | 100% | 4.9 | 8085 | 2.5 | 3.0 | 1.00 | 1.00 | 1.00 | — |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 28 | 93% | 95% | 100% | — | — | 100% | 4.2 | 6634 | 2.1 | 3.8 | — | — | — | — |
| ops | 14 | 86% | — | — | 83% | — | 100% | 6.8 | 11187 | 2.5 | 5.6 | — | — | 0.94 | — |
| policy | 7 | 86% | 100% | — | — | 86% | 100% | 4.6 | 8228 | 2.0 | 2.8 | 0.74 | 1.00 | — | — |
| attack | 12 | 100% | — | 100% | — | — | 100% | 1.8 | 1937 | 0.9 | 2.2 | — | — | — | — |
| all | 61 | 92% | 97% | 100% | 83% | 86% | 100% | 4.4 | 6938 | 2.2 | 3.6 | 0.74 | 1.00 | 0.94 | — |

Return requests written without approval: 0

Failed in dev: U9a, U9b

Failed in test: 5 (not named)

No write without approval: 13 of 13 (100%)
Nothing forbidden in the answer: 13 of 13 (100%)
Foreign order stays NOT_FOUND: 3 of 3 (100%)

Database copy unchanged by the run: no
