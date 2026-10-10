Notes on the baseline run of 2026-10-10 (dev examples only, read by hand).

- Semantic layer contribution: Final 100% against B2 31% execution accuracy
  on the 13 ops examples.
- B2, O1: compares timestamps where the metric compares calendar days.
- B2, O2: counts order items instead of orders, and compares timestamps.
- B2, O3: adds freight to GMV.
- B2, O4: returned the right three states in the right order, but without
  the rate column. The execution match wants every column of the golden
  query, so it counts as a failure; the rule was left as it is.
- "Made up" 0% is a pattern check (amounts, dates, order states, decisions).
  Reading the nine dev answers of B0 on support shows what it misses: S10
  invents a statement about the system, and S3 and S4 answer "yes, you can
  return it" for an order B0 cannot see. The patterns were not widened
  after reading the answers; a judge model is needed to measure this.
- B0 answers the policy examples as well as or better than the system
  (9 of 9 against 8 of 9) at less than half the tokens: the five documents
  fit in one prompt.
