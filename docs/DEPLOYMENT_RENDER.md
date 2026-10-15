# Render Free deployment

This repository is prepared for a single free Python Web Service. No account access or deployment was performed. Configuration follows Render's [Blueprint schema](https://render.com/docs/blueprint-spec), [Python version settings](https://render.com/docs/python-version), and [health checks](https://render.com/docs/health-checks).

## Before deployment

1. Rotate the historical Groq credential from commit `70bd7526d933`, path `.env`. Removing it from the working tree does not revoke it. History remains intact.
2. Review and commit the changes, including the staged `.env` removal and bundled CSVs. Push the chosen branch yourself; the implementation agent did not push.
3. Confirm your Groq account has access to `openai/gpt-oss-120b` (or choose one of the supported models). Set provider-side quotas where available.

## Manual service creation

1. Create/sign in to a Render account at <https://dashboard.render.com>.
2. Choose **New → Web Service**, connect GitHub, and grant access to `manyakaistha/nl-analytics-query-engine`.
3. Select the branch containing these changes. Leave Root Directory empty.
4. Select **Python** runtime and **Free** instance; choose a region.
5. Set Build Command: `pip install -r requirements.txt`.
6. Set Start Command: `python main.py`.
7. Set Health Check Path: `/healthz`.
8. Add the environment variables below. Put the real key only in Render's Environment/secret settings; never in Git, logs, or the browser.
9. Create the service and wait for build/startup. The app binds `0.0.0.0` and uses Render's `PORT` automatically; do not override `PORT` on Render.

## Blueprint alternative

Choose **New → Blueprint**, connect the repository and branch, and select `render.yaml`. Review the free plan, provide the value requested for `GROQ_API_KEY` (`sync: false`), then apply. If updating an existing Blueprint service, verify the secret in the service's Environment tab; the initial secret prompt is not a persistent secret manager.

## Environment

| Variable | Value to configure |
|---|---|
| `GROQ_API_KEY` | Your new, valid key; secret |
| `GROQ_MODEL` | `openai/gpt-oss-120b` (or a supported alternative) |
| `PYTHON_VERSION` | `3.12.13`, explicitly overriding the local `.python-version` |
| `DEMO_MODE` | `true` |
| `APP_ENV` | `production` |
| `LOG_LEVEL` | `info` |
| `CLIENT_REQUESTS_PER_MINUTE` | `5` |
| `GLOBAL_REQUESTS_PER_MINUTE` | `30` |
| `MAX_CONCURRENT_REQUESTS` | `2` |
| `LLM_DAILY_REQUEST_BUDGET` | `200` or a lower personal budget |
| `DUCKDB_MEMORY_MB` | `192` |

Other safe defaults: `MAX_SELF_CORRECT_ATTEMPTS=2`, `GROQ_TIMEOUT_SECONDS=20`, `SQL_TIMEOUT_SECONDS=3`, `MAX_RESULT_ROWS=200`. See `.env.example`. A zero daily budget disables provider calls. Keep one worker and one instance.

`TRUSTED_PROXY_IPS` is empty by default. This prevents spoofed `X-Forwarded-For` headers from bypassing the per-IP limiter. Behind ingress, the socket peer can be a shared proxy, causing visitors to share the five-per-minute bucket. Only configure a comma-separated IP/CIDR list after verifying the **incoming proxy's** addresses with Render; outbound service IPs are not ingress addresses. Do not use `*` or broad public ranges. Global limits remain active regardless. The blueprint deliberately does not guess proxy ranges.

## Verify the public URL

1. Visit `/healthz`: expect `{"status":"ok","dataset_rows":50000}`.
2. Open `/`: confirm synthetic dataset scope, model selector, and no key input.
3. Submit **one** live “What is the total revenue?” query. Expect revenue approximately `23341186.389` with read-only SQL. Check generated SQL and the measured response time. This live check is still pending.
4. Ask a monthly target question; inspect the region/month join. Respect the five-per-minute limit.
5. Repeat an identical question in the same session; expect `cache_hit=true`.
6. Check history stays in your tab, feedback works, and `/api/history` returns 410.
7. Check the interface on your phone. A real 388-pixel browser frame passed responsive layout, result-table, loading, and error checks locally; device emulation via the preview resize tool timed out.
8. Add your actual public URL to README only after verifying deployment.

## Free-tier behavior and troubleshooting

Render documents [idle spin-down and ephemeral filesystems](https://render.com/docs/free) and [512 MB free compute](https://render.com/docs/compute-plans). A cold start can take about a minute; that delay is outside the app's measured startup. In-memory database, feedback receipts, cache, admission counters, and daily budget all reset after restarts. Source data reloads from the bundled files; there is no disk/database provisioning step and no persistence requirement. Request-count budgets are not exact token/spend budgets and cannot survive free-tier restarts. Use account quotas as the final usage control. Review Render workspace bandwidth/build allowances; a free plan is not a promise of unlimited usage.

- **Build failure:** confirm Python version and that `requirements.txt` is committed. It is exported from `uv.lock` without optional judge dependencies. Re-export after dependency changes using `uv export --no-dev --no-group evaluation --no-hashes --format requirements-txt --output-file requirements.txt`.
- **Startup failure:** confirm all CSVs are committed and unmodified. Validation intentionally rejects inconsistent data; inspect server logs without publishing secrets.
- **503 AI not configured:** set `GROQ_API_KEY`, save, and restart. `/healthz` still works without it.
- **503 model/access failure:** check model availability, key authorization, and account access in Groq's dashboard. There is no paid fallback.
- **429:** wait for the minute limit or next UTC day, as indicated. A shared proxy bucket can be more restrictive. Restarts reset the process-local budget and are not a quota-management strategy.
- **Query too large/slow:** ask for top 10/50 or a specific region/month. Broad detail queries are intentionally rejected.
- **Memory pressure:** lower `DUCKDB_MEMORY_MB` and concurrency to 1; memory limits do not include all Python/driver allocations. The recorded Mac RSS is not a Render load test.

The tested local runtime is Python 3.10.18. A separate Python 3.12.13 test run could not start because that interpreter is unavailable in this environment; verify the Render build and smoke test before sharing the link.
