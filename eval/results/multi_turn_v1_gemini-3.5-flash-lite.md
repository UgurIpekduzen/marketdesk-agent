multi_turn_set.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 16 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| multi | 4 | 100% | 100% | 100% | — | — | 100% | 9.5 | 15753 | 4.1 | 5.6 | — | — | — | — |
| all | 4 | 100% | 100% | 100% | — | — | 100% | 9.5 | 15753 | 4.1 | 5.6 | — | — | — | — |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| multi | 12 | 100% | 100% | 100% | — | — | 100% | 7.0 | 11454 | 2.7 | 4.6 | — | — | — | — |
| all | 12 | 100% | 100% | 100% | — | — | 100% | 7.0 | 11454 | 2.7 | 4.6 | — | — | — | — |

Return requests written without approval: 0

Failed in dev: none

Failed in test: 0 (not named)

Requests as expected after the clicks: 16 of 16

Passed per flow, dev only: M1 1 of 1, M3 1 of 1, M6 1 of 1, M8 1 of 1

Database copy unchanged by the run: no
