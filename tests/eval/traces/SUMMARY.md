# Evaluation trace index

Start with the [evaluation trace and improvement history](../../../docs/EVALUATION_TRACE.md) for the stage comparison, charts, prompt and code changes, case-level failures, and measurement limits.

| Trace | Coverage | Status |
|---|---:|---|
| [R0 summary](2026-09-23T09-40_R0/summary.md) · [results](2026-09-23T09-40_R0/results.jsonl) | 8/8 | Baseline; old scalar scorer understated correct one-cell answers |
| [Early R1 results](2026-09-23T09-47_R1/results.jsonl) | 27/30 | Stopped by Gemini quota; T4.6 mutated the shared in-memory database |
| [Complete Groq review](2026-09-23T10-30_groq/combined_review.md) · [combined results](2026-09-23T10-30_groq/results.complete.jsonl) | 30/30 | Canonical complete run; final nine cases used the second key |

The `2026-09-23T10-30_groq/results.jsonl` and its `summary.md` were written before all failed/quota cases were rerun. Use `results.complete.jsonl` and `combined_review.md` for complete-run totals. The `2026-09-23T10-46_groq/` directory contains the nine-case continuation.

Each JSONL row contains the question ID, response (including generated SQL and result), confidence, latency, and either oracle correctness or expected behavior. There was one run per question; no prompt snapshot or commit hash is stored with these traces.
