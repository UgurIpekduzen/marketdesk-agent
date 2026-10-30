# Embedding models on the policy questions (asked in English)

20 questions, 28 policy sections, quantized ONNX on CPU. A figure that differs between ways of embedding the sections is given as: all at once (as the policy index is built) / in batches of 10 / one at a time.

| Model | Vector | First | Top 3 | Top 5 | MRR | Worst rank | Query p50 (ms) | Peak memory (MB) |
|---|---|---|---|---|---|---|---|---|
| e5-small | 384 | 7 / 6 / 8 | 12 / 12 / 14 | 15 / 14 / 15 | 0.515 / 0.483 / 0.572 | 25 / 21 / 14 | 3.7 / 4.0 / 2.9 | 678 |
| e5-base | 768 | 11 / 11 / 12 | 18 / 18 / 16 | 19 / 18 / 18 | 0.722 / 0.713 / 0.735 | 14 / 11 / 7 | 7.0 / 7.5 / 6.9 | 921 |
| bge-m3 | 1024 | 17 / 14 / 17 | 19 / 20 / 19 | 19 / 20 / 19 | 0.892 / 0.817 / 0.892 | 6 / 3 / 6 | 21.7 / 21.7 / 21.3 | 1340 |

## Revisions

- e5-small: `Xenova/multilingual-e5-small` at `761b726dd34fb83930e26aab4e9ac3899aa1fa78`
- e5-base: `Xenova/multilingual-e5-base` at `1ec9243030a27d1a115d5c340572074c125b58b2`
- bge-m3: `Xenova/bge-m3` at `4de13258303883538bd53b696b452bf8099f0858`
