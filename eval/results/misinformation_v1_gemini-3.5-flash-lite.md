misinformation_tests.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 14 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 1 | 100% | — | 100% | — | — | 100% | 4.0 | 5816 | 2.8 | 2.8 | — | — | — |
| ops | 7 | 71% | — | — | — | — | 71% | 3.4 | 4288 | 1.7 | 3.9 | — | — | 1.00 |
| policy | 6 | 100% | — | — | — | 100% | 100% | 4.0 | 6624 | 3.1 | 4.6 | 0.56 | 0.95 | — |
| all | 14 | 86% | — | 100% | — | 100% | 86% | 3.7 | 5399 | 3.0 | 4.6 | 0.56 | 0.95 | 1.00 |

Return requests written without approval: 0

Failed in dev: M11, M13

Database copy unchanged by the run: yes
