# Evaluation on the synthetic dataset

The 2026-09 traces, charts, test plan, Round 1 report, and old architecture illustrations are historical. They describe the original small dataset. They are preserved, not reused as accuracy evidence for this application.

## Executed checks — 2026-10-15

- **45 offline unittest tests passed, 0 failed, 0 skipped**, Python 3.10.18. [Actual output](benchmarks/20261015-offline-tests.txt).
- Source validation passed: 50,000 lines; 33,347 orders; 8,424 customers; 9 unique region/month targets; January–March 2024. Numeric ranges, nulls, dates, categorical hierarchies, order/customer consistency, and decimal revenue were checked.
- All **17 oracle SQL queries** in `tests/eval/queries.yaml` execute within the public result limits. This validates oracle queries, not model generation. T3.3/T3.7 now explicitly request deterministic top-50 results instead of unbounded detail lists.
- All 8 curated SQL prompt examples execute against the real data.
- A real, expensive cross join was interrupted by DuckDB after a 30 ms test timer; the next query succeeded. Production defaults to 3 seconds. This demonstrates interruption on the installed version; it is not a universal guarantee for every native operation.
- Formatter/lint checks for modified Python and `git diff --check` passed.
- A Python 3.12.13 test attempt could not start: no matching interpreter was available. Render uses this explicitly configured runtime; its build/smoke check remains pending.

The suite uses no real keys and makes no external LLM requests. It covers SQL writes/multiple statements, files/network/table functions, recursive CTEs, unapproved tables/functions, oversize results, healthy analytical queries, parsing, sanitized failures, quota/rate errors, missing keys, cache isolation/invalidation, stale processing, feedback isolation/expiry, concurrent overload, and duplicate requests.

## Local benchmark

Run:

```bash
uv sync --no-group evaluation
uv run --no-group evaluation python -m scripts.benchmark --runs 5
```

The command creates a new timestamped JSON artifact. It executes real DuckDB queries, then replaces only model generation with verified SQL fixtures and measures FastAPI requests via TestClient. Admission limits are raised only inside that isolated benchmark process so repeated calls can be measured; production settings are not changed. Cache-miss/hit results are compared and provider mock call counts asserted. Do not interpret this as an NLP accuracy test.

Final captured run: [20261015T085102282406Z-offline.json](benchmarks/20261015T085102282406Z-offline.json), macOS arm64 / Python 3.10.18, five repetitions per case, twelve analytical cases.

| Measurement | Recorded value |
|---|---:|
| Data validation and in-memory database initialization | 364.616 ms |
| Peak benchmark-process RSS | 123.53 MiB |
| Prompt length | 6,027 characters |
| Median across per-case median SQL times | 1.310 ms |
| Median across per-case median mocked API cache misses | 1.966 ms |
| Median across per-case median mocked API cache hits | 0.541 ms |

Cases include total/region/category/monthly revenue, category profit, AOV, customers, products, segments, repeat customers, margins, and target comparisons. Per-case SQL, results, and timings are retained. Earlier timestamped files are implementation snapshots, not controlled before/after comparisons. No speedup percentage is claimed. Mac measurements are not Render performance guarantees; RSS includes Python/driver allocations, and DuckDB's memory setting is not a process RSS cap.

Responses expose prompt, generation, SQL validation, DuckDB execution, and model serialization timings. Actual client calls additionally expose provider-request and model-parsing stages. Mocked generation has no actual provider-request latency. Cache hits report zero new model/SQL work. Frontend rendering duration is recorded with `performance.now()` in the session history entry. A measured desktop scalar render took 35.6 ms in the shared preview; this is one observation, not a benchmark distribution.

## Browser verification

`uv run --no-group evaluation python -m tests.frontend_fixture` starts an explicit **offline-only** fixture on port 8001. It uses predetermined SQL and the real bundled DuckDB data; do not deploy this entry point. Port 8000 uses the normal application.

In the shared browser, checked: home/model loading, all four example question shapes across desktop and responsive views, loading/disabled states, total revenue, regional/AOV/target results, SQL disclosure, feedback, history restoration, and a simulated timeout message with controls restored. Desktop layout had no horizontal overflow. Viewport-resize calls timed out, so responsive CSS was checked using the same HTML/CSS/JS in a real 388-pixel `srcdoc` browser frame: page width was 373 pixels, textarea 335 pixels, and the mobile sidebar switched to static layout. Physical phone and screen-reader testing remain pending. Screenshots in README show the real local UI; target results use the mocked provider fixture.

## Live evaluation — pending

The current system has **no newly measured text-to-SQL accuracy, live Groq latency, or live Render latency**. Standard tests must never consume real provider quota.

After configuring the server key, deliberately run a small live sample:

```bash
uv run python main.py
uv run python -m tests.eval.run_groq_eval --ids T1.1 T2.3
```

The runner uses the same source loader/decimal schema as the application, respects five requests per minute, records model/dataset fingerprint/timings/errors, and writes a unique new trace directory. It no longer copies or resets legacy feedback logs. Verify the deployed dataset version matches the local oracle before evaluating a remote service. Error codes distinguish provider failures, SQL failures, unsafe SQL, and resource limits. Scores compare normalized result values/output shapes; behavioral questions still require manual review.

A full catalog includes date filters, CTEs, window functions, target joins, ambiguity, unsupported history/metrics, prompt injection, and write requests. Review assumptions and generated SQL as well as row matches; an execution success is not evidence of a correct answer. The optional Gemini judge is preserved in the `evaluation` dependency group and requires separate credentials/quota. Its model/access must also be checked before use. No judge, live model, or provider billing test was run here.

## Verification after restoring the original UI

The original pre-edit design has been restored with current dataset copy and secure API integrations. The backend protections and cache remain intact. Latest suite: **46 passed, 0 failed, 0 skipped** in 1.365 seconds ([output](benchmarks/20261015-restored-ui-tests.txt)). A new API regression verifies whitespace-normalized cache hits, unchanged results, zero generation attempts on the hit, fresh feedback receipts and model-specific cache invalidation. All eight original suggestion SQL fixtures execute against the complete dataset. Browser checks covered the actual original suggestion button, cached badge, formatted/highlighted SQL, clipboard copy, feedback, downloaded CSV content and responsive width of 388 pixels without horizontal overflow. These checks used the offline fixture; they do not establish live LLM accuracy. Styles can be rebuilt using the command in `static/vendor/README.md`.
