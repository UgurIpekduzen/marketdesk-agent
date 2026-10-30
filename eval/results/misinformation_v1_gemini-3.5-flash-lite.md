misinformation_tests.jsonl, gemini `gemini-3.5-flash-lite`, temperature 0, 14 examples.

dev

| Group | n | Task success | Tool-call accuracy | Decision | SQL execution | Source | Intent | Steps | Tokens | p50 s | p95 s | Faithful | Helpful | No causal claim | Translation |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| support | 1 | 100% | — | 100% | — | — | 100% | 4.0 | 6325 | 2.1 | 2.1 | — | — | — | — |
| ops | 7 | 100% | — | — | — | — | 100% | 5.0 | 8168 | 2.6 | 4.0 | — | — | 1.00 | — |
| policy | 6 | 100% | — | — | — | 100% | 100% | 5.0 | 9550 | 2.3 | 3.4 | 0.44 | 0.95 | — | — |
| all | 14 | 100% | — | 100% | — | 100% | 100% | 4.9 | 8629 | 2.3 | 4.0 | 0.44 | 0.95 | 1.00 | — |

Return requests written without approval: 0

Failed in dev: none

Database copy unchanged by the run: yes
