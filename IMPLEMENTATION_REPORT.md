# Implementation report — 2026-10-15

**Final verdict: READY WITH MINOR MANUAL STEPS.** The local application, full synthetic dataset, offline tests, and deployment configuration are prepared. Rotate the exposed historical credential, configure Render, and complete a live provider/deployment smoke test before publishing the demo. No push, history rewrite, external account access, or deployment was performed.

## A. Changes made

Preserved the existing FastAPI, DuckDB, Groq, module structure, evaluation tools, and plain HTML/CSS/JavaScript stack. Integrated the attached source files without changing their bytes. Replaced stale processed-file loading with validated source loading. Hardened generated SQL and the public API. Removed public global history and browser key collection. Added deterministic result explanations, bounded private caching, provider budgets, resource controls, an improved responsive UI, offline acceptance coverage, reproducible measurements, and Render documentation.

## B. Files modified or added

| Files | Purpose |
|---|---|
| `.env` (index removal only), `.env.example`, `.gitignore`, `.gitattributes` | Preserve local secrets, stop tracking `.env`, document settings, preserve supplied CSV bytes/CRLF |
| `app/config.py` | Validated environment thresholds, primary key preference and placeholder-safe legacy fallback |
| `app/database.py` | Validated decimal loading, AST/table/function restrictions, result/memory bounds, safe interrupt timer |
| `app/limits.py` | Bounded client/global rate buckets, provider concurrency, UTC daily call budget/token counters |
| `app/llm.py` | Explicit SDK timeout, disabled implicit retries, bounded parsing, stage timings, safe token logging |
| `app/engine.py` | Bounded correction/backoff, sanitized failures, no retries for unsafe/resource errors, grounded explanations, stage timings, duplicate suppression |
| `app/cache.py` | Bounded session/credential/prompt/model/dataset-scoped LRU with 15-minute TTL |
| `app/feedback.py` | No persistent raw history; temporary opaque, expiring, session-bound feedback receipts |
| `app/models.py`, `app/server.py` | Bounded schemas, no request-value echo on validation failures, streaming body/time limit, admission controls, HTTP errors, health, security headers, session isolation, threaded work |
| `app/prompts.py` | Compact schema/actual categories, order-line metrics, safe target joins, reviewed examples, unsupported-period guidance |
| `main.py` | Production host/PORT, one worker, no reload, explicit proxy trust validation, configured logging |
| `data/sales_data.csv`, `data/targets.csv`, `data/DATASET_SUMMARY.json` | Supplied dataset and summary |
| `data/archive/original/{sales_data.csv,targets.csv,data_dictionary.json,nl_queries.json}` | Original inputs backed up before replacement/correction |
| `data/data_dictionary.json`, `data/nl_queries.json` | Distinct-order/AOV metrics and reviewed active examples |
| `scripts/preprocess.py`, `scripts/validate_data.py` | Fingerprinted deterministic derived outputs and strict source validation |
| `scripts/benchmark.py` | Repeatable real-SQL / mocked-API measurements with timestamped artifacts |
| `static/index.html`, `static/style.css`, `static/app.js` | Dependency-free UI, examples, results/SQL, CSV export, private session history, feedback, accessible responsive controls |
| `tests/test_regressions.py`, `tests/test_public_demo.py` | Updated prior tests plus new offline data/security/API/privacy/reliability checks |
| `tests/frontend_fixture.py` | Explicit offline-only browser fixture; never production startup |
| `tests/eval/queries.yaml`, `tests/eval/run_eval.py`, `tests/eval/run_groq_eval.py` | Bounded oracle lists, current source loader, optional judge, metadata, unique traces, pacing, no legacy feedback copying |
| `pyproject.toml`, `uv.lock`, `requirements.txt` | SQLGlot parser; removed unused Anthropic dependency; Gemini judge optional; locked deployment export |
| `render.yaml`, `docs/DEPLOYMENT_RENDER.md` | Free single-service blueprint and exact manual/Blueprint deployment instructions |
| `README.md`, `docs/EVALUATION_CURRENT.md` | Current product, architecture, privacy, configuration, evaluation and limitations |
| `docs/TEST_PLAN.md`, `docs/ROUND1_RESULTS.md`, `docs/EVALUATION_TRACE.md` | Mark prior small-dataset reports explicitly historical; preserve their results |
| `docs/benchmarks/*`, `docs/screenshots/sales-lens-{home,targets}.png` | Actual offline measurements/test log and local browser screenshots |

Generated `data/processed/` files remain ignored. Existing historical traces, charts, illustrations and screenshots were preserved; they are not current accuracy evidence.

## C. Dataset integration

| Check | Result |
|---|---|
| Sales rows / columns | 50,000 / 15; exact expected column names |
| Distinct orders / customers | 33,347 / 8,424 |
| Repeat customers | 6,584, using distinct orders |
| Date range | 2024-01-01 through 2024-03-31 |
| Targets | 9 rows, 3 columns, unique region/month, matching sales dimensions |
| Revenue | 23,341,186.3890 |
| Supplied profit | 3,090,849.13 |
| Dataset SHA-256 fingerprint | `9da31fb58bd81e97e9d8251d505c01e0c085a78555aee2ec1140007954202e37` |

Sales columns: `order_id`, `order_date`, `region`, `country`, `city`, `customer_id`, `customer_segment`, `product_category`, `product_subcategory`, `product_name`, `quantity`, `unit_price`, `discount`, `shipping_cost`, `profit`. Target columns: `region`, `month`, `target_revenue`.

Validated schemas, nulls, finite numbers, positive integer quantities/order IDs, fractional discounts in [0,1], nonnegative price/shipping, dates, categories, product/geography hierarchies, stable order/customer dimensions, and target uniqueness/coverage. Decimal CSV calculations independently agree with DuckDB totals and region/month aggregates. No data correction or regeneration was necessary. Revenue excludes shipping; profit is summed as supplied, without assuming whether shipping is already included. Currency is unspecified. No other years were invented. Source changes require process restart; the running database and its fingerprint represent an immutable startup snapshot.

## D. Security improvements

- `.env` is ignored and absent from Git's index; the developer's local file still exists. Current tracked files had no matches for the scanned Groq/Google/Anthropic secret patterns. This is a scoped scan, not a proof against every secret format.
- **Historical exposure:** `.env` in commit `70bd7526d933` contains a Groq credential-shaped value. Rotate/revoke that key. Its value was never printed or copied into documentation. History was not rewritten.
- Public AI requests: 5 per socket-client minute, 30 globally per minute, 2 concurrent pipelines/provider calls, 200 provider calls per UTC day, at most 2 attempts per question, explicit 20-second SDK timeout, no implicit SDK retry or provider fallback. 429 responses indicate limits/budget exhaustion.
- SQLGlot parses a single SELECT/set query, rejects mutating/multiple statements, recursive CTEs, arbitrary/table functions, unapproved tables/functions and qualified external catalogs. DuckDB binds columns against only loaded tables. External access is disabled and configuration locked after trusted initialization.
- DuckDB uses one execution thread, 192 MB memory setting, no temporary spill, a 3-second interrupt timer, max 200 result rows / 40 columns / 128 KiB. Timer cancellation/join occurs under the connection lock before another query can run.
- API bodies are limited to 8 KiB with a 10-second body-read deadline; questions to 1,000 characters. No wildcard CORS. Responses include CSP, anti-framing, nosniff, same-origin referrer and no-store policy. Browser output uses DOM text, not model/user HTML; CSV export escapes formula prefixes.
- Global history returns 410. Queries are not written to feedback logs. Browser history holds at most 10 answers; cache is session-scoped and bounded. Feedback uses opaque receipts, same-session cookies, 15-minute expiry and bounded storage. No raw feedback enters model prompts.
- Raw exceptions, stack traces, keys and request validation inputs are not returned or logged by application error handling. Actual provider usage logs contain model, tokens and elapsed time only.

## E. Performance results

Final captured benchmark: `docs/benchmarks/20261015T085102282406Z-offline.json`, macOS arm64 / Python 3.10.18, 12 cases × 5 repetitions:

- Data validation/database initialization: **364.616 ms**.
- Peak benchmark-process RSS: **123.53 MiB**.
- Prompt: **6,027 characters**.
- Median across case-median SQL times: **1.310 ms**.
- Median across case-median mocked API cache misses/hits: **1.966 / 0.541 ms**.

Groq was mocked; no live Groq latency, token cost, speedup, generation accuracy or Render performance was measured. Prompt, model/request/parsing, SQL validation/execution and serialization timings are available in responses where applicable. Browser scalar rendering was observed at 35.6 ms once. Full methodology and earlier retained iteration artifacts are in `docs/EVALUATION_CURRENT.md`.

## F. Test results

Final executed suite: `uv run --no-group evaluation python -m unittest discover -s tests -p 'test_*.py' -v` — **45 passed, 0 failed, 0 skipped**, 1.565 seconds on Python 3.10.18. Actual log is under `docs/benchmarks/20261015-offline-tests.txt`. Formatting/lint checks and `git diff --check` passed. The source validator, optional preprocessing, 8 curated examples, 17 catalog oracle queries and 12-case benchmark ran successfully. These counts are not model accuracy scores.

Browser checks used a real running UI and mocked provider SQL executed on the real data: all four example shapes, loading/disabled controls, scalar/regional/AOV/target results, SQL disclosure, feedback, session-history reload, responsive layout and simulated provider timeout. A real 388-pixel browser frame had no horizontal overflow; physical-device/screen-reader checks remain manual. The preview's viewport-resize operation timed out. Python 3.12.13 tests could not start because the interpreter was unavailable locally. The installed Starlette test adapter emits a non-failing httpx deprecation warning.

## G. Deployment readiness

`render.yaml` configures one Python Free Web Service, `pip install -r requirements.txt`, `python main.py`, health path `/healthz`, and a dashboard-provided secret. Python 3.12.13 is explicitly selected. No persistent filesystem or database provisioning is required; startup reads the bundled data once. Health and UI work without a key; AI returns a friendly 503 until configured. No reload or multiple workers are enabled.

The blueprint follows current official Render documentation, but it has not been submitted to Render or tested on its Linux/CPU/RAM allocation. Read `docs/DEPLOYMENT_RENDER.md` for precise settings and troubleshooting.

## H. Remaining manual steps

1. Rotate/revoke the key historically committed in `.env`.
2. Review/commit the changes and push the desired branch yourself.
3. Connect the GitHub repository to Render and create the free Web Service manually or through the blueprint.
4. Set `GROQ_API_KEY`, `GROQ_MODEL`, `DEMO_MODE=true`, `APP_ENV=production`, `LOG_LEVEL=info`, `PYTHON_VERSION=3.12.13` and desired budgets. Render provides `PORT`.
5. Verify the build/runtime and health, perform a small live Groq smoke test, inspect target joins, test on a phone, then add the public URL to README.
6. If needed, verify actual ingress proxy IPs with Render before setting `TRUSTED_PROXY_IPS`. Never trust wildcard/unverified forwarding headers.

## I. Known limitations

Process-local limits, caches, budgets and feedback reset after restart/cold start. They do not provide global guarantees with multiple workers/instances. Request counts are not exact token or monetary budgets; provider-side quotas remain necessary. Default proxy distrust may place visitors behind a shared ingress into one rate bucket. DuckDB's memory limit does not bound total Python RSS, and timer interruption is not an OS sandbox. SDK timeouts are network-operation limits, not a hard process wall-clock deadline. Source data is reloaded only on restart. Function allowlisting intentionally rejects uncommon SQL; ordinary joins/CTEs/aggregates/date/window patterns are tested. Prompt injection cannot be solved by prompts alone; SQL capabilities and resources are separately restricted. Model logic/confidence remain untrusted and confidence is uncalibrated. Feedback is temporary, no longer a persistent training/history log. Charts were optional and were not added. Live model accuracy, deployed resource use, physical-device accessibility and Python 3.12 runtime verification remain pending. Historical documentation/artifacts retain their old context and are explicitly identified as such.

## J. Final verdict

**READY WITH MINOR MANUAL STEPS** for a bounded portfolio demo after credential rotation and a successful live deployment/provider smoke test. This verdict does not claim a completed deployment, verified live model accuracy, or enterprise production readiness.

## UI restoration requested after implementation

Restored the pre-edit interface from `b64b7c4:static/index.html`: the original warm palette, Instrument Serif / Inter / JetBrains Mono fonts, centered chat, suggestion cards, rounded composer, model selector, confidence/timing/cache badges, formatted SQL/copy and reasoning sections. Updated only the dataset/disclaimer copy and integrations needed by the new API. The public UI continues using the server-managed key and temporary feedback receipts. Session history, CSV export, timeout/error handling and result bounds remain available. Backend implementation was not reverted.

Original external assets are now vendored with licenses and the original Tailwind theme is precompiled (`scripts/tailwind.config.cjs`, `static/ui-custom.css`, `static/style.css`, `static/vendor/`). No server CSP relaxation was needed. Inline event handlers were replaced with event listeners. Build instructions are in `static/vendor/README.md`; deployment requires no Node process. Current screenshots are `docs/screenshots/analytics-home.png` and `analytics-targets.png`; earlier screenshots are retained as historical implementation artifacts.

Restoration verification: **46 passed, 0 failed, 0 skipped** in 1.365 seconds; see `docs/benchmarks/20261015-restored-ui-tests.txt`. The additional API regression verifies a whitespace-only repeat uses the session cache, performs no extra generation, gets a fresh feedback receipt, and a model change causes a cache miss. All eight original example SQL fixtures execute on the real dataset. Browser checks passed for the original suggestion button, cache badge, SQL highlighting/copy, feedback, CSV content, reload/history and a real 388-pixel frame with no horizontal overflow. LLM generation remained mocked; no live Groq requests were made.

## Floating glass history panel

Added `static/history-dock.js` and `static/history-dock.css` as an isolated frontend module, integrated through `static/index.html` and `static/app.js`. The existing palette, fonts, composer and result cards remain. A translucent, blurred floating panel shows six recent conversations. Its bottom “+” opens a searchable native dialog containing up to 30 chats; selecting a conversation restores its stored answers without querying the API. New chat starts a fresh conversation while preserving previous ones. History is session-local, limited to ten answers per conversation and 2 MiB total. Existing response caching and the backend are unchanged.

The panel collapses to an icon rail on smaller desktops and a glass history control on mobile. Keyboard focus, Escape dismissal, active states, busy-query protection, reduced-motion rules and a non-blur fallback are included. No canvas, animation loop, service or dependency was added.

Verification: all **46 existing offline tests passed** (1.432 seconds), plus **18 browser acceptance assertions** in `tests/browser/history-dock-checks.js`. Checks cover six recent / thirty retained chats, ordering, search, restore without API calls, conversation updates, busy state, safe text rendering and history retained by New chat. Additional browser checks confirmed reload persistence, 16px backdrop blur, Escape/focus restoration and a 388px frame without horizontal page overflow. Browser fixtures were removed and the prior tab history restored after checks. No live Groq requests were made.

## Shared glass styling and architecture page

Created checkpoint commit `c96bda3` before resuming this design update; it contains the completed backend, restored original UI, dataset and Recent chats panel. The local `.env` was not committed and nothing was pushed.

Added `static/glass-theme.css` and updated `static/index.html` to extend the existing history panel's translucent material and hover behavior to cards, composer, model/send controls, result bubbles and other pills. The logo/title sit in their own glass bubble above the sidebar, now positioned at the top-left. The Recent chats module and CSS remain byte-identical to the checkpoint. GitHub and Architecture pills sit below it; repository links follow the configured Git origin.

Added `static/architecture.html`, `static/architecture.css` and `static/architecture.js`. The page uses semantic, selectable HTML stages over a decorative Retina-scaled canvas. Seeded background geometry is generated once, animated packet progress uses elapsed time with clamped deltas and smoothstep easing, and animation stops when paused, hidden or offscreen. New-question and cache-hit routes reflect the implementation; reduced motion uses manual step controls. Startup validation, retries, privacy, resource limits and source modules are explained without making live provider requests.

Verification: **46 offline backend tests passed**, unchanged from the checkpoint. `tests/browser/architecture-checks.js` passed **11 browser assertions** covering stages, details, cache bypass, DPR sizing, moving/paused canvas, overflow and zero API requests. `tests/browser/architecture-responsive-checks.js` passed **7 assertions** for narrow layout and static/manual reduced-motion behavior. The chat UI was checked at 390px with no horizontal overflow, a visible glass title bubble, a compact sidebar and both project links. The original response cache and backend source match checkpoint `c96bda3`; no live Groq call was made.

Added an About the data page and sidebar pill, with verified source counts, field definitions, target join rules, metric formulas and coverage limits. Updated shared styling and generated Tailwind assets to mint green and white; history layout and backend behavior are retained. Checked desktop and 390px data layouts and verified the page totals directly against the CSVs.

Restored the previous warm neutral palette at user request, retaining the Data page, sidebar pill and stable architecture detail layout.

Added a source-linked Evaluations page and sidebar pill, separating historical GPT-OSS 120B evidence from current offline tests/benchmarks and explicitly identifying missing comparative/live evidence. Rewrote README around the product, setup, data, architecture, evaluation and deployment. No live provider evaluation was invoked.

Evaluations page verified at 1100px and 390px: no page overflow, mobile table scrolls within its container, reproduction disclosure opens, and all ten evidence links resolve to existing repository files. Reported benchmark medians were recomputed from the stored JSON; the recorded 46-test result was checked against its output artifact.

Added a shared compact navigation rail to Data, Architecture and Evaluations with direct chat/page/GitHub links, hover/focus expansion and current-page indication. Mobile uses a compact bottom dock with reserved footer space. All three companion layouts checked at 1100px and 390px without horizontal overflow; navigation makes no API calls.

Unified companion-page sidebar with the home page by reusing workspace-dock, dock-brand, dock-links and dock-link styles. Moved each title pill into the sidebar and removed the separate header navigation. Desktop and mobile widths retain shared glass, pill dimensions and responsive behavior; checked 1440px, 1100px and 390px without page overflow.

Added a shared right-hand reading contents dock to the companion pages. It derives anchors from semantic section headings, shows scroll progress, and marks the active section. Wide screens show contents by default; smaller screens use a native expandable disclosure. Verified anchors and open/closed layouts at 1440px, 1100px and 390px without overflow, and confirmed a real section jump updates the URL, scroll position, active entry and progress.

Contents now opens near the page top on all screen sizes and automatically collapses after scrolling beyond 64px. It reopens when returning to the top; manual reopening supports jumps and collapses on continued downward scrolling. Verified top/open, scroll/closed, manual reopen and resumed-scroll collapse in the browser.

Updated README with six fresh screenshots of the running current UI: home, target results, expanded SQL/reasoning, Data, Architecture and Evaluations. Images are preserved under docs/screenshots/current with capture provenance. Query screenshots use the explicit offline fixture and real bundled DuckDB data; no live model inference or quota was used.
