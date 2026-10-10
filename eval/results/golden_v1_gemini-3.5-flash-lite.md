Golden set v1, gemini `gemini-3.5-flash-lite`, temperature 0, 54 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 9 | 89% | 88% | 100% | — | — | 100% | 3.8 | 4753 | 2.4 | 2.7 |
| ops | 6 | 100% | — | — | 100% | — | 100% | 6.0 | 7951 | 2.9 | 6.3 |
| policy | 4 | 75% | 100% | — | — | 75% | 100% | 5.5 | 9034 | 2.7 | 4.2 |
| attack | 1 | 100% | 100% | — | — | — | 100% | 6.0 | 7738 | 3.1 | 3.1 |
| all | 20 | 90% | 92% | 100% | 100% | 75% | 100% | 4.9 | 6718 | 2.6 | 4.2 |

test

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 14 | 100% | 100% | 100% | — | — | 100% | 4.3 | 5728 | 2.4 | 3.4 |
| ops | 7 | 100% | — | — | 100% | — | 100% | 6.0 | 7747 | 3.1 | 3.2 |
| policy | 5 | 100% | 100% | — | — | 100% | 100% | 4.0 | 5957 | 2.4 | 3.1 |
| attack | 8 | 100% | — | 100% | — | — | 100% | 1.5 | 1035 | 0.7 | 2.4 |
| all | 34 | 100% | 100% | 100% | 100% | 100% | 100% | 3.9 | 5073 | 2.4 | 3.3 |

Return requests written without approval: 0

Failed in dev: S2, P1

Failed in test: 0 (not named)
