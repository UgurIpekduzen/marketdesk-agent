# Embedding models on the policy questions

20 questions, 28 policy sections, quantized ONNX on CPU. A figure that differs between ways of embedding the sections is given as: all at once (as the policy index is built) / in batches of 10 / one at a time.

| Model | Vector | First | Top 3 | Top 5 | MRR | Worst rank | Query p50 (ms) | Peak memory (MB) |
|---|---|---|---|---|---|---|---|---|
| e5-small | 384 | 14 / 14 / 15 | 18 / 17 / 17 | 18 | 0.806 / 0.793 / 0.822 | 8 / 8 / 9 | 2.3 / 3.0 / 2.1 | 676 |
| e5-base | 768 | 13 / 13 / 16 | 16 / 17 / 17 | 17 / 19 / 19 | 0.746 / 0.781 / 0.852 | 8 / 6 / 11 | 6.8 / 7.0 / 7.0 | 928 |
| bge-m3 | 1024 | 16 / 17 / 16 | 19 | 19 / 20 / 19 | 0.872 / 0.893 / 0.883 | 9 / 5 / 6 | 22.3 / 22.2 / 22.4 | 1344 |

## Revisions

- e5-small: `Xenova/multilingual-e5-small` at `761b726dd34fb83930e26aab4e9ac3899aa1fa78`
- e5-base: `Xenova/multilingual-e5-base` at `1ec9243030a27d1a115d5c340572074c125b58b2`
- bge-m3: `Xenova/bge-m3` at `4de13258303883538bd53b696b452bf8099f0858`
