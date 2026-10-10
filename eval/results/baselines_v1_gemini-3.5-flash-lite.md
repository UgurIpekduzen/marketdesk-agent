Baselines on golden set v1, gemini `gemini-3.5-flash-lite`, temperature 0.

| System · group | n | Task success | SQL execution | Source | Made up | Steps | Tokens | p50 s | p95 s |
|---|---|---|---|---|---|---|---|---|---|
| B0 · support | 23 | 4% | — | — | 0% | 1.0 | 3279 | 1.0 | 1.3 |
| B0 · policy | 9 | 100% | — | 100% | 0% | 1.0 | 3271 | 1.0 | 1.2 |
| B1 · policy | 9 | 89% | — | 89% | 0% | 1.0 | 776 | 0.8 | 1.0 |
| B2 · ops | 13 | 31% | 31% | — | — | 1.0 | 682 | 0.9 | 1.4 |
| Final · support | 23 | 96% | — | — | — | 4.1 | 5347 | 2.4 | 3.3 |
| Final · ops | 13 | 100% | 100% | — | — | 6.0 | 7841 | 3.1 | 6.3 |
| Final · policy | 9 | 89% | — | 89% | — | 4.7 | 7324 | 2.7 | 4.2 |
| Final · attack | 9 | 100% | — | — | — | 2.0 | 1780 | 0.8 | 3.1 |

Task success of a baseline is its own rule: for B0 on support, the text checks pass, the example needs no tool and nothing is made up; on policy, the text checks pass and the right section is cited; for B2, the rows equal the rows of the golden query. "Made up" is a pattern check, not a judgement.
