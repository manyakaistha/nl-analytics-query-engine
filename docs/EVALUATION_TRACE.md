# Evaluation trace and improvement history

This document connects the original test campaign, the prompt and code revisions, and the saved evaluation traces. It distinguishes **measured results**, **manual review**, and **planned checks** so a reader can follow the evidence without treating every score as directly comparable.

## At a glance

| Stage | Questions run | What it measured | Recorded outcome | Main qualification |
|---|---:|---|---|---|
| R0 baseline | 8 Tier 1–2 development cases | First prompt and initial scoring harness | Mean **66.0/100**; **2/8** scored ≥80 | Numeric scalar results were scored incorrectly |
| Early R1 | 27 of 30 catalog cases | First prompt tune on a broader set | Mean **55.8/100**; **6/27** scored ≥80 | Three cases were not reached; `DELETE` changed the shared database during the run |
| Revised prompt, complete Groq run | 30 of 30 cases | Revised prompt and application safeguards with `openai/gpt-oss-120b` | **30/30** executed; **15/17** exact oracle shapes; **11/13** behavior cases passed manual review | One run per case; Gemini judge unavailable; small dataset |
| App smoke check | 3 query calls plus route checks | End-to-end API and new cache | Correct total sales; whitespace repeat hit cache; paraphrase missed | Focused route check, not a catalog rerun |
| Regression suite | 12 checks | SQL guard, scoring, feedback, rate limit and cache behavior | **12/12 passed** when run after cache implementation | Deterministic checks; does not measure model accuracy |

The complete run used two Groq API keys in sequence after the first reached its daily token quota. The canonical complete result is [`results.complete.jsonl`](../tests/eval/traces/2026-09-23T10-30_groq/results.complete.jsonl), with a human review in [`combined_review.md`](../tests/eval/traces/2026-09-23T10-30_groq/combined_review.md).

## What was evaluated

The [30-question catalog](../tests/eval/queries.yaml) is split into four tiers. Seventeen questions have executable DuckDB oracle SQL. Thirteen Tier 4 questions have an expected behavior instead of a single numeric oracle.

| Tier | Cases | Main skills and failure modes | Evaluation method |
|---|---:|---|---|
| 1 — warm-up | 4 | Synonyms, basic filtering, distinct orders, date interpretation | SQL oracle |
| 2 — multi-step | 5 | Regional rankings, revenue share, AOV, missing sales in target joins | SQL oracle |
| 3 — hard analytics | 8 | Windows, period growth, nested aggregates, margins, target gaps | SQL oracle |
| 4 — adversarial | 13 | Missing years, undefined metrics, no-match filters, typos, SQL writes, prompt disclosure | Behavior specification and manual review in the complete run |

The data has **10 orders** across January–March 2024. Targets exist for three regions and three months. That makes answers easy to verify exactly, but it is too small to establish performance on larger production data.

### Catalog coverage

| IDs | Cases |
|---|---|
| T1.1–T1.4 | Total sales; Consumer order count; EMEA earnings; India revenue in March |
| T2.1–T2.5 | Top two cities per region; category revenue share; AOV by region; January missed targets; best-selling product per region |
| T3.1–T3.4 | Month-over-month growth; Q1 target attainment; orders above average; segment share within region |
| T3.5–T3.8 | Profit margin; shipping cost share; repeat customers and spend; largest target gap by region |
| T4.1–T4.4 | YoY with one year; last month; Japan with no orders; daily target from a monthly target |
| T4.5–T4.8 | Undefined churn; delete request; system prompt request; misspelled APAC product request |
| T4.9–T4.13 | Geography synonym; category pivot by month; city vs target; drop-table request; sales for 2025 |

The catalog labels 22 cases `dev` and 8 `holdout`. The eventual curated examples include a near match to holdout T2.5, so holdout status here is **not** proof of generalization. The test plan described a three-run median protocol, but the saved R0, R1, and complete Groq artifacts contain **one run per question**.

## Stage-by-stage evidence

### R0: eight-case baseline

The first run covered T1.1–T1.4 and T2.1–T2.4. The harness reported a mean of **66.0/100**, with **2/8** at or above 80. The trace revealed two especially useful failures: India revenue in March was mishandled (T1.4), and the target comparison omitted a region with zero January sales (T2.4). The early scorer also gave correct one-cell numeric answers partial credit because the API formatted a scalar as a string.

Sources: [R0 summary](../tests/eval/traces/2026-09-23T09-40_R0/summary.md) and [R0 per-query trace](../tests/eval/traces/2026-09-23T09-40_R0/results.jsonl).

### Early R1: expanded but incomplete

The first tune taught the model to start target comparisons from `targets`, use a `LEFT JOIN`, anchor month names to the dataset year, and return only requested columns. The harness expanded to all 30 catalog questions, but stopped after **27** when the Gemini judge hit quota. Its reported mean was **55.8/100**, with **6/27** at or above 80.

On the same eight IDs used in R0, the recorded mean rose from **66.0** to **82.1**, and the number scoring at least 80 rose from **2** to **4**. This is the narrowest numeric before/after view available, though the shared old scoring defects still apply. In particular, T2.4 changed from **0/45** to **45/45** correctness under that harness. T1.4 was assigned **30/45** despite returning the right numeric value, reflecting the scalar comparison defect.

```text
Old-harness score, same eight questions (0–100)
R0  66.0  █████████████░░░░░░░
R1  82.1  ████████████████░░░░
          0        50       100
```

The wider R1 mean is lower because 19 harder cases were added and several failed. This run is also **not a clean safety evaluation**: T4.6 executed a `DELETE` against the shared in-memory table. Later answers used changed data. T4.7 counted seven orders instead of ten, and T4.9 had no EMEA rows. Those later results cannot be interpreted as independent prompt failures.

For a more consistent oracle comparison, the current result comparator was reapplied offline to each saved response: **R0 5/8 exact**, **early R1 10/17 exact**, and **complete Groq run 15/17 exact**. This corrects the scalar-string scoring defect across the saved outputs, but it cannot equalize changes in prompt, model settings, or application code. The [case-by-case matrix](charts/oracle-case-matrix.svg) shows every oracle question, including shape and partial matches.

Sources: [early R1 trace](../tests/eval/traces/2026-09-23T09-47_R1/results.jsonl) and [historical R1 report](ROUND1_RESULTS.md). The latter was written before the scorer and data-corruption issues were fully accounted for.

### Revised prompt and complete Groq run

After reviewing the early R1 trace, the prompt was rebuilt around live dataset facts, explicit business definitions, supported and unsupported metrics, SQL dialect guidance, answer shape, and calibrated confidence rules. A code-level SQL guard was also added. A later Groq-only runner completed all 30 cases with `openai/gpt-oss-120b` after the Gemini judge returned 429 quota errors.

```text
Complete Groq run, single attempt per question
SQL executed       30/30  ████████████████████  100%
Exact oracle shape 15/17  ██████████████████░░   88%
Behavior pass      11/13  █████████████████░░░   85%  manual review
```

| Tier | Oracle cases | Exact result shape | Notes |
|---|---:|---:|---|
| 1 | 4 | 4 | All warm-up values and shapes matched |
| 2 | 5 | 4 | T2.4 returned the correct regions and extra actual/target metrics |
| 3 | 8 | 7 | T3.4 returned correct shares but omitted raw revenue |
| **Total** | **17** | **15** | Exact-shape scoring is stricter than semantic correctness |

The thirteen Tier 4 cases were manually reviewed: **11 pass, 1 fail, 1 partial**. The fail was T4.2, which selected February 2024 for “last month” with confidence 0.93 even though March was the latest data month under the prompt's anchor. The partial case was T4.11: it selected the expected city, but its target denominator included only the city's sales month (**10,000**) instead of all target months (**28,500**). T4.13 used the literal 2025 filter and explained the lack of data, but its confidence **0.45** was slightly above the prompt's stated cap.

Median latency was **39.8 seconds** and the 90th percentile was **44.3 seconds** for this model/run. The assembled prompt was about **20,039 characters**. These are observed figures, not a model comparison or a latency guarantee.

Sources: [complete review](../tests/eval/traces/2026-09-23T10-30_groq/combined_review.md) and [complete machine-readable trace](../tests/eval/traces/2026-09-23T10-30_groq/results.complete.jsonl). The individual Groq run folders contain partial attempts; use the combined trace for the 30-case totals.

## What changed and why

| Failure or weakness found | Prompt/data change | Code or evaluation change | Evidence after change / remaining issue |
|---|---|---|---|
| Zero-sales target rows disappeared | Require `targets LEFT JOIN` aggregated sales and `COALESCE` actuals to zero | Curated executable examples replace pseudo-SQL | R1 T2.4 scored 45/45; complete run returned the right regions, with extra useful columns |
| “Only requested columns” hid the number supporting rankings | Return the dimension **and** the metric that justifies selection; omit helper rank columns | Curated examples follow that shape | T2.5, T3.3, T3.7 and T3.8 were exact oracle matches in the complete run; T3.4 still differed in shape |
| Wrong quarter, percentage scale, or gap sign | Define quarter aggregation, 0–100 percentages, and gap as actual minus target | — | T3.2, T3.5 and T3.8 were exact oracle matches in the complete run |
| Relative dates followed the real calendar or an unsupported month | Build a live profile of sales date range, available months and values; anchor relative dates to latest data month | Profile read from DuckDB at prompt construction | Explicit March/2025 cases handled; “last month” still failed at T4.2 |
| Fabricated YoY baseline or churn formula; invalid DuckDB functions | Define behavior for missing data and undefined metrics; add DuckDB dialect notes | Self-correction retry message points to valid columns and dialect | T4.1 and T4.5 passed manual review |
| A generated `DELETE` actually ran | Require one read-only `SELECT` and refusal behavior | Parse SQL and reject non-`SELECT`/multiple statements; disable DuckDB external access after data load | Delete and drop requests passed manual review; deterministic guard checks passed |
| Raw feedback could become system-prompt instructions | Use only aggregate negative-feedback/error counts | Feedback summary strips raw query, SQL and error text | Regression check confirms raw injected text is absent from prompt context |
| Scalar answers scored as partial despite correct values | — | Normalize numeric scalar strings and compare rows with their values | Complete run scored all four Tier 1 oracle cases exact |
| Tier 4 was scored as always incorrect in early harness | — | Full harness now asks Gemini to judge expected behavior; Groq-only runner records behavior for manual review | Complete run has explicit pass/partial/fail review, not a fabricated numeric Tier 4 score |
| Reprocessing overwrote improved few-shots | Keep reviewed examples as source data | Preprocessor reads `data/nl_queries_curated.json` for processed examples | Reviewed runnable examples persist across preprocessing |
| Repeated identical questions cost another model call | — | Bounded, process-local LRU response cache keyed by normalized question, prompt, data hash and model settings | Route smoke check: whitespace repeat hit cache; paraphrase called Groq |
| Need to compare model choices in the UI | — | Added selection among GPT OSS 120B, GPT OSS 20B and Qwen 3.8 27B; model is part of the cache key | Only GPT OSS 120B has the documented complete 30-case run |

The source files for these changes are [`app/prompts.py`](../app/prompts.py), [`app/database.py`](../app/database.py), [`app/engine.py`](../app/engine.py), [`app/feedback.py`](../app/feedback.py), [`app/cache.py`](../app/cache.py), [`scripts/preprocess.py`](../scripts/preprocess.py), and the evaluation harnesses under [`tests/eval/`](../tests/eval/).

## Trace index and reproducibility notes

| Artifact | What it contains | How to use it |
|---|---|---|
| [Test plan](TEST_PLAN.md) | Original design, catalog rationale and desired multi-round protocol | Historical intent; some planned steps were not run |
| [R0 summary](../tests/eval/traces/2026-09-23T09-40_R0/summary.md) / [JSONL](../tests/eval/traces/2026-09-23T09-40_R0/results.jsonl) | Eight-case baseline scores, SQL, results and judge notes | Inspect initial behavior; account for scalar scoring bug |
| [Early R1 JSONL](../tests/eval/traces/2026-09-23T09-47_R1/results.jsonl) | 27 case responses and scores | Trace first prompt tune; later cases were affected by the executed delete |
| [Complete Groq review](../tests/eval/traces/2026-09-23T10-30_groq/combined_review.md) | Per-case exact-match and manual behavior review | Human-readable final campaign result |
| [Complete Groq JSONL](../tests/eval/traces/2026-09-23T10-30_groq/results.complete.jsonl) | Full SQL, response, confidence, latency and oracle comparison for 30 cases | Inspect individual cases or recompute summary statistics |
| [Regression suite](../tests/test_regressions.py) | Deterministic checks for guards, scoring, feedback and cache | Verify code paths without Groq or Gemini calls |

The earlier [test plan](TEST_PLAN.md) envisioned prompt snapshots, commit hashes, failure-code files, three runs per question, and a score trend across rounds. Those artifacts and repetitions are **not present** in the saved traces. The old `run_eval.py` JSONL also hardcodes `round: 0` and `prompt_version: v0` even inside its R1 directory; use the directory timestamp and code history to identify that stage. Because the runs were not all performed with the same scorer, judge availability, model settings, database state, or question set, the numbers above should not be read as a controlled causal estimate of each individual fix.

The complete Groq run used manual Tier 4 judgment because Gemini quota blocked the judge. A future controlled comparison should pin the exact prompt and model, reset the database and feedback state before each run, repeat each question, and record the resulting variability. It should also target the remaining T4.2 and T4.11 failures and test the other selectable models before making comparative performance claims.
