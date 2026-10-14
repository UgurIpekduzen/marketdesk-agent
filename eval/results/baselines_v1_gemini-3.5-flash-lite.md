Baselines on golden set v1, gemini `gemini-3.5-flash-lite`, temperature 0.

| System · group | n | Task success | SQL execution | Source | Made up | Steps | Tokens | p50 s | p95 s | Faithful | Helpful |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0 · support | 37 | 14% | — | — | 0% | 1.0 | 3281 | 1.0 | 1.6 | — | — |
| B0 · policy | 13 | 100% | — | 100% | 0% | 1.0 | 3274 | 0.9 | 1.2 | 0.92 | 1.00 |
| B1 · policy | 13 | 92% | — | 91% | 0% | 1.0 | 751 | 0.8 | 1.1 | 0.92 | 0.88 |
| B2 · ops | 19 | 37% | 37% | — | — | 1.0 | 684 | 0.9 | 1.4 | — | — |
| Final · support | 37 | 97% | — | — | — | 4.2 | 5434 | 2.4 | 19.6 | — | — |
| Final · ops | 21 | 95% | 95% | — | — | 6.3 | 8411 | 3.1 | 18.7 | — | — |
| Final · policy | 13 | 92% | — | 91% | — | 4.6 | 7187 | 2.9 | 46.3 | 0.95 | 1.00 |
| Final · attack | 13 | 100% | — | — | — | 2.0 | 1850 | 0.8 | 32.6 | — | — |

Task success of a baseline is its own rule: for B0 on support, the text checks pass, the example needs no tool and nothing is made up; on policy, the text checks pass and the right section is cited; for B2, the rows equal the rows of the golden query. "Made up" is a pattern check, not a judgement.
