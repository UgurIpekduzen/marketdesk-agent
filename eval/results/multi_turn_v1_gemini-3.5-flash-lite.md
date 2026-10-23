multi_turn_set.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 16 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| multi | 4 | 100% | 100% | 100% | — | — | 100% | 9.0 | 13808 | 5.9 | 12.8 | — | — | — |
| all | 4 | 100% | 100% | 100% | — | — | 100% | 9.0 | 13808 | 5.9 | 12.8 | — | — | — |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| multi | 12 | 83% | 90% | 83% | — | — | 100% | 7.2 | 10833 | 4.3 | 13.3 | — | — | — |
| all | 12 | 83% | 90% | 83% | — | — | 100% | 7.2 | 10833 | 4.3 | 13.3 | — | — | — |

Return requests written without approval: 0

Failed in dev: none

Failed in test: 2 (not named)

Requests as expected after the clicks: 16 of 16

Passed per flow, dev only: M1 1 of 1, M3 1 of 1, M6 1 of 1, M8 1 of 1

Database copy unchanged by the run: no
