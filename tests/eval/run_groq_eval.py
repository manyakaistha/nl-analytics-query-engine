"""Run the query catalog against Groq without an external LLM judge.

The saved trace includes every response for manual review. Deterministic
correctness is scored only where the catalog supplies oracle SQL.
"""

import argparse
import json
import time
from datetime import datetime

import httpx
import yaml

from tests.eval.run_eval import (
    API_URL,
    DATA_DIR,
    QUERIES_FILE,
    TRACES_DIR,
    compare_results,
    normalize_result,
    setup_duckdb,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="*", help="Run only these query IDs")
    parser.add_argument("--api-url", default=API_URL, help="Query endpoint to evaluate")
    args = parser.parse_args()
    queries = yaml.safe_load(QUERIES_FILE.read_text(encoding="utf-8"))["queries"]
    if args.ids:
        selected = set(args.ids)
        queries = [query for query in queries if query["id"] in selected]
        if len(queries) != len(selected):
            parser.error("Unknown query ID in --ids")
    oracle = setup_duckdb()
    trace_dir = TRACES_DIR / f"{datetime.now().strftime('%Y-%m-%dT%H-%M')}_groq"
    trace_dir.mkdir(parents=True, exist_ok=True)

    feedback = DATA_DIR / "feedback_log.csv"
    original_feedback = feedback.read_bytes() if feedback.exists() else None
    if original_feedback is not None:
        (trace_dir / "feedback_log.before.csv").write_bytes(original_feedback)
        feedback.write_bytes(original_feedback.splitlines(keepends=True)[0])

    records = []
    try:
        with httpx.Client(timeout=90) as client:
            for i, query in enumerate(queries, 1):
                expected = None
                if "oracle_sql" in query:
                    expected = normalize_result(oracle.execute(query["oracle_sql"]).fetchall())

                start = time.monotonic()
                try:
                    response = client.post(args.api_url, json={"query": query["question"]})
                    response.raise_for_status()
                    actual = response.json()
                except Exception as exc:
                    actual = {"result": f"Error: {exc}", "attempts": 0,
                              "confidence_score": 0, "generated_sql": "", "explanation": ""}

                result = actual.get("result")
                error = isinstance(result, str) and result.lower().startswith("error:")
                correctness = None
                if expected is not None:
                    correctness = 0 if error else compare_results(expected, normalize_result(result))
                record = {
                    "query_id": query["id"],
                    "tier": query["tier"],
                    "split": query["split"],
                    "question": query["question"],
                    "expected_behaviour": query.get("expected_behaviour"),
                    "oracle_result": expected,
                    "response": actual,
                    "executes": not error,
                    "correctness": correctness,
                    "latency_ms": round((time.monotonic() - start) * 1000),
                }
                records.append(record)
                with (trace_dir / "results.jsonl").open("a", encoding="utf-8") as file:
                    file.write(json.dumps(record, default=str) + "\n")
                print(f"[{i}/{len(queries)}] {query['id']}: "
                      f"{'error' if error else 'ok'}, correctness={correctness}, "
                      f"confidence={actual.get('confidence_score')}, "
                      f"attempts={actual.get('attempts')}", flush=True)
                time.sleep(2)
    finally:
        if original_feedback is not None:
            feedback.write_bytes(original_feedback)

    scored = [r for r in records if r["correctness"] is not None]
    exact = sum(r["correctness"] == 45 for r in scored)
    executed = sum(r["executes"] for r in records)
    summary = (
        f"# Groq evaluation\n\n"
        f"- Queries: {len(records)}\n"
        f"- Executed: {executed}/{len(records)}\n"
        f"- Exact oracle matches: {exact}/{len(scored)}\n"
        f"- Behaviour cases for manual review: {len(records) - len(scored)}\n"
        f"- Median latency: {sorted(r['latency_ms'] for r in records)[len(records)//2]} ms\n"
        f"\nSee `results.jsonl` for SQL, responses, and per-case scores.\n"
    )
    (trace_dir / "summary.md").write_text(summary, encoding="utf-8")
    print(summary, flush=True)
    print(f"Trace: {trace_dir}", flush=True)


if __name__ == "__main__":
    main()
