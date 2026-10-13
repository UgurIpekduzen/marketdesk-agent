Golden set v1, gemini `gemini-3.5-flash-lite`, temperature 0, 84 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 9 | 89% | 88% | 100% | — | — | 100% | 3.8 | 4753 | 2.4 | 2.7 |
| ops | 7 | 86% | — | — | 86% | — | 100% | 6.0 | 7922 | 3.3 | 265.9 |
| policy | 6 | 83% | 100% | — | — | 75% | 100% | 5.3 | 8684 | 2.9 | 61.4 |
| attack | 1 | 100% | 100% | — | — | — | 100% | 6.0 | 7738 | 3.1 | 3.1 |
| all | 23 | 87% | 93% | 100% | 86% | 75% | 100% | 5.0 | 6873 | 2.7 | 61.4 |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 28 | 100% | 100% | 100% | — | — | 100% | 4.3 | 5653 | 3.4 | 268.7 |
| ops | 14 | 100% | — | — | 100% | — | 100% | 6.3 | 8403 | 3.2 | 377.7 |
| policy | 7 | 100% | 100% | — | — | 100% | 100% | 4.0 | 5908 | 2.7 | 59.7 |
| attack | 12 | 100% | — | 100% | — | — | 100% | 1.7 | 1359 | 0.9 | 80.5 |
| all | 61 | 100% | 100% | 100% | 100% | 100% | 100% | 4.2 | 5469 | 3.2 | 260.2 |

Return requests written without approval: 0

Failed in dev: S2, P1, U13a

Failed in test: 0 (not named)
