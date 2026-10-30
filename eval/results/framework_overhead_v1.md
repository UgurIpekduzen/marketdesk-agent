# Framework overhead: LlamaIndex FunctionAgent without the model

200 runs per row after 5 warm-up runs, CPU, a stand-in model that answers at once and a tool that does nothing. The time is the framework's plus the project's own run_agent around it, and the stand-in's own bookkeeping (it records every request), so it is an upper bound for the framework.

| Model calls in a run | Run p50 (ms) | Run p95 (ms) | Run max (ms) | Step p50 (ms) | Step p95 (ms) | Build p50 (ms) |
|---|---|---|---|---|---|---|
| 1 | 4.49 | 6.78 | 44.48 | 4.49 | 6.78 | 0.61 |
| 2 | 8.28 | 10.43 | 19.53 | 4.14 | 5.22 | 0.65 |
| 4 | 15.53 | 18.39 | 51.02 | 3.88 | 4.6 | 0.64 |
| 8 | 32.12 | 52.13 | 98.37 | 4.02 | 6.52 | 0.74 |

For scale: the model took 751.4 ms per call in the 25 development examples of the golden set (83 calls). The framework's step above is 0.54% of that.
