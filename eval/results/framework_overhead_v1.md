# Framework overhead: LlamaIndex FunctionAgent without the model

200 runs per row after 5 warm-up runs, CPU, a stand-in model that answers at once and a tool that does nothing. The time is the framework's plus the project's own run_agent around it, and the stand-in's own bookkeeping (it records every request), so it is an upper bound for the framework.

| Model calls in a run | Run p50 (ms) | Run p95 (ms) | Run max (ms) | Step p50 (ms) | Step p95 (ms) | Build p50 (ms) |
|---|---|---|---|---|---|---|
| 1 | 4.59 | 5.96 | 42.0 | 4.59 | 5.96 | 0.64 |
| 2 | 8.64 | 10.39 | 13.23 | 4.32 | 5.2 | 0.66 |
| 4 | 16.22 | 18.82 | 57.52 | 4.06 | 4.7 | 0.66 |
| 7 | 27.78 | 32.37 | 66.96 | 3.97 | 4.62 | 0.68 |

Every run ended with an answer.

For scale: the model took 751.4 ms per call in the 25 development examples of the golden set (83 calls). The framework's step above is 0.53% of that.
