# Framework overhead: LlamaIndex and Pydantic AI without the model

200 runs per row after 5 warm-up runs, CPU, one process. A scripted model that answers at once and a tool that does nothing; a run of n model calls asks for the tool n - 1 times and then answers. One scenario: it says nothing about quality, features, memory or tracing, and a faster step is not a better one.

| Way | Model calls | Run p50 (ms) | Run p95 (ms) | Step p50 (ms) | Step p95 (ms) | Build p50 (ms) |
|---|---|---|---|---|---|---|
| LlamaIndex, bare agent.run | 1 | 4.44 | 6.23 | 4.44 | 6.23 | 0.62 |
| LlamaIndex, bare agent.run | 2 | 7.97 | 11.52 | 3.99 | 5.76 | 0.64 |
| LlamaIndex, bare agent.run | 4 | 15.06 | 17.11 | 3.76 | 4.28 | 0.64 |
| LlamaIndex, bare agent.run | 7 | 24.94 | 28.45 | 3.56 | 4.06 | 0.65 |
| LlamaIndex, through run_agent | 1 | 4.54 | 4.98 | 4.54 | 4.98 | 0.6 |
| LlamaIndex, through run_agent | 2 | 8.31 | 10.32 | 4.16 | 5.16 | 0.65 |
| LlamaIndex, through run_agent | 4 | 16.1 | 20.06 | 4.03 | 5.02 | 0.68 |
| LlamaIndex, through run_agent | 7 | 26.74 | 31.95 | 3.82 | 4.56 | 0.7 |
| Pydantic AI 2.63.0 | 1 | 1.9 | 2.27 | 1.9 | 2.27 | 0.48 |
| Pydantic AI 2.63.0 | 2 | 3.22 | 3.74 | 1.61 | 1.87 | 0.51 |
| Pydantic AI 2.63.0 | 4 | 5.85 | 6.57 | 1.46 | 1.64 | 0.56 |
| Pydantic AI 2.63.0 | 7 | 9.69 | 10.57 | 1.38 | 1.51 | 0.59 |
| LangChain 1.4.7 create_agent (on LangGraph) | 1 | 0.98 | 1.28 | 0.98 | 1.28 | 2.27 |
| LangChain 1.4.7 create_agent (on LangGraph) | 2 | 2.24 | 2.77 | 1.12 | 1.39 | 2.27 |
| LangChain 1.4.7 create_agent (on LangGraph) | 4 | 4.57 | 5.87 | 1.14 | 1.47 | 2.37 |
| LangChain 1.4.7 create_agent (on LangGraph) | 7 | 7.9 | 8.89 | 1.13 | 1.27 | 2.46 |

Versions: llama-index-core 0.14.25, pydantic-ai-slim 2.63.0, langchain 1.4.7, langgraph 1.2.19, langchain-core 1.7.3.

For scale: the model took 751.4 ms per call in the 25 development examples of the golden set (83 calls).
