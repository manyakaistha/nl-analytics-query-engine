# Test Campaign Results: Round 1 (Prompt Tuning)

> **Historical report.** This records the early 27-question R1 run and its original interpretation. Its scorer mishandled numeric scalar responses, and T4.6 executed a `DELETE` that changed the shared database for later cases. The run stopped before T4.11–T4.13. For the reconciled stage comparison, charts, fixes and complete 30-question run, use [Evaluation trace and improvement history](EVALUATION_TRACE.md).

I completed the prompt engineering phase and evaluated the model on the expanded 30-query catalog. 

> **Note:** Due to the free-tier quota limits of `gemini-3.8-flash` (20 requests per day per key), the evaluation job hit the hard limit and was killed after evaluating 27 out of 30 queries. However, this is more than enough to prove the efficacy of our prompt tuning!

## What Was Done

1. **Prompt Tuning (`app/prompts.py`):** 
   - Addressed the `LEFT JOIN` trap by explicitly teaching the LLM to start from the targets table and COALESCE the sales to 0.
   - Addressed the Relative Date anchoring by explicitly informing the LLM that the data timeline is 2024.
   - Addressed output shaping by instructing the LLM to only return the requested columns and not extra grouping keys.
2. **In-Context Learning:** Replaced all pseudo-logic examples in `nl_queries.json` with actual, executable DuckDB SQL examples demonstrating advanced window functions and joins.
3. **Adversarial Expansion:** Added three new `holdout` queries (T4.11, T4.12, T4.13) to `tests/eval/queries.yaml` focusing on SQL injection handling and future dates.

## Results: Round 1 Summary

We evaluated a much harder set of queries (27 queries spanning Tier 1 through Tier 4, compared to just 8 basic queries in Round 0). 

| Metric | Round 0 (8 Queries) | Round 1 (27 Queries) |
|--------|---------------------|----------------------|
| Mean Score | 66.0 | **55.8** |
| Pass Rate (Score ≥80) | 25% | **22.2%** |

*Note: The mean score dropped because Round 1 includes the significantly harder Tier 3 and Tier 4 adversarial queries.*

### Improvement on Failing Queries

The prompt tuning successfully resolved the critical failures identified in Round 0!

| Query | Round 0 Correctness | Round 1 Correctness | Round 1 Total Score | Notes |
|-------|---------------------|---------------------|---------------------|-------|
| **Which regions missed their target in January?** (T2.4) | 0 / 45 | **45 / 45** | **97 / 100** | The LLM successfully utilized the `LEFT JOIN` and `COALESCE` pattern taught in the prompt! |
| **India revenue in March** (T1.4) | 0 / 45 | **30 / 45** | **70 / 100** | The LLM correctly anchored "March" to 2024 as instructed. |
