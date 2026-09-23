"""
Evaluation harness for the Intelligent Analytics Query Engine.

Hits POST /api/query, compares results against DuckDB oracle,
and uses Gemini 3.1 Pro as the LLM judge for explanation/SQL quality.

Gemini API keys are multiplexed round-robin across GEMINI_API_KEY_0..3
to avoid per-key rate limits.
"""

import json
import logging
import math
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import httpx
import yaml
from dotenv import load_dotenv
from google import genai

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_URL = "http://localhost:8000/api/query"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
TRACES_DIR = PROJECT_ROOT / "tests" / "eval" / "traces"
QUERIES_FILE = PROJECT_ROOT / "tests" / "eval" / "queries.yaml"

GEMINI_MODEL = "models/gemini-3.8-flash"
NUM_KEYS = 4  # GEMINI_API_KEY_0 … GEMINI_API_KEY_3

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------
JUDGE_PROMPT = """\
You are an expert SQL judge evaluating an Intelligent Analytics Query Engine.
Score explanation quality and SQL quality, and score behaviour correctness when an expected behaviour is provided.

Here is the context:
Question: {question}

Generated SQL:
```sql
{generated_sql}
```

Generated Explanation:
{explanation}

API Result: {result}
Confidence: {confidence}
Expected behaviour (when provided): {expected_behaviour}

Please evaluate the following dimensions and provide a score for each:

1. Explanation Quality (0 to 15 points)
   - 15: States interpretation, states assumptions clearly, describes the method, consistent with SQL and numbers.
   - 10: Mostly accurate but misses a minor assumption or filter.
   - 5: Vague, misses key interpretation of business logic, or slightly inconsistent with SQL.
   - 0: Hallucinated numbers, completely contradictory to SQL, or empty.

2. SQL Quality (0 to 10 points)
   - 10: No hard-coded literal answers, uses correct metric definitions, no unnecessary cross joins, correct join type (e.g. LEFT JOIN when appropriate).
   - 5: Works but is inefficient or uses a suboptimal join/grouping.
   - 0: Hard-codes answers, completely incorrect logic for the metrics, mutates data, or completely invalid SQL.

3. Behaviour correctness (0, 15, 30, or 45 points; only when expected behaviour
   is provided). Check the SQL, explanation, result and confidence against that
   expectation. Award 45 only when all essential conditions hold, 30 for a
   minor omission, 15 for partial compliance, and 0 for contradiction or unsafe
   behaviour. A refusal must not claim that a data change succeeded.

Return your evaluation as a strictly valid JSON object (no markdown wrapping) in this exact format:
{{
  "explanation_score": <int>,
  "sql_score": <int>,
  "behaviour_score": <int>,
  "notes": "<string containing your reasoning>"
}}
"""

# ---------------------------------------------------------------------------
# Gemini key multiplexer
# ---------------------------------------------------------------------------

class GeminiPool:
    """Round-robin pool of google.genai clients keyed to GEMINI_API_KEY_0…3."""

    def __init__(self) -> None:
        self._clients: list[genai.Client] = []
        for i in range(NUM_KEYS):
            key = os.environ.get(f"GEMINI_API_KEY_{i}")
            if key:
                self._clients.append(genai.Client(api_key=key))
                logger.info(f"  Loaded GEMINI_API_KEY_{i}")
            else:
                logger.warning(f"  GEMINI_API_KEY_{i} not found — skipping")
        if not self._clients:
            raise RuntimeError("No GEMINI_API_KEY_* keys found in environment")
        self._idx = 0

    def _next_client(self) -> genai.Client:
        client = self._clients[self._idx % len(self._clients)]
        self._idx += 1
        return client

    def judge(self, question: str, generated_sql: str, explanation: str,
              result: Any = None, confidence: float = 0,
              expected_behaviour: str = "") -> Dict[str, Any]:
        prompt = JUDGE_PROMPT.format(
            question=question,
            generated_sql=generated_sql,
            explanation=explanation,
            result=json.dumps(result, default=str),
            confidence=confidence,
            expected_behaviour=expected_behaviour or "None; omit this score",
        )
        last_err = None
        # Try each key; on 429 wait and retry with next key
        for attempt in range(len(self._clients) * 2):  # 2 full rotations
            client = self._next_client()
            try:
                resp = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config={
                        "temperature": 0.2,
                        "max_output_tokens": 1024,
                    },
                )
                text = resp.text
                start = text.find("{")
                end = text.rfind("}") 
                if start != -1 and end != -1:
                    return json.loads(text[start : end + 1])
                return {
                    "explanation_score": 0,
                    "sql_score": 0,
                    "notes": f"Failed to parse judge JSON: {text[:200]}",
                }
            except Exception as exc:
                last_err = exc
                err_str = str(exc)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait = min(5 * (attempt + 1), 30)
                    logger.warning(f"  Rate limited, waiting {wait}s before rotating key…")
                    time.sleep(wait)
                elif "401" in err_str or "UNAUTHENTICATED" in err_str:
                    logger.warning(f"  Key auth failed, skipping to next key…")
                    time.sleep(0.5)
                else:
                    logger.warning(f"  Judge call failed ({exc}), rotating key…")
                    time.sleep(1)
        logger.error(f"  All judge keys exhausted: {last_err}")
        return {"explanation_score": 0, "sql_score": 0, "notes": f"All keys failed: {last_err}"}

# ---------------------------------------------------------------------------
# DuckDB oracle
# ---------------------------------------------------------------------------

def setup_duckdb() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(database=":memory:")
    sales_csv = DATA_DIR / "sales_data.csv"
    targets_csv = DATA_DIR / "targets.csv"
    conn.execute(f"CREATE TABLE sales_data AS SELECT * FROM read_csv_auto('{sales_csv}')")
    conn.execute(f"CREATE TABLE targets AS SELECT * FROM read_csv_auto('{targets_csv}')")
    conn.execute(
        "CREATE VIEW sales_with_revenue AS "
        "SELECT *, (quantity*unit_price*(1-discount)) as revenue FROM sales_data"
    )
    return conn

# ---------------------------------------------------------------------------
# Result normalisation & comparison
# ---------------------------------------------------------------------------

def normalize_result(res: Any) -> List[tuple]:
    """Convert API result (scalar / list-of-dicts) and oracle result (list-of-tuples)
    into a canonical sorted list of rounded tuples for comparison."""
    if not isinstance(res, list):
        if res == "No results found." or (isinstance(res, str) and res.startswith("Error:")):
            return []
        # Scalar — wrap
        val = _normalize_value(res)
        return [(val,)]
    normalized = []
    for row in res:
        if isinstance(row, dict):
            tup = tuple(_normalize_value(v) for v in row.values())
        elif isinstance(row, (list, tuple)):
            tup = tuple(_normalize_value(v) for v in row)
        else:
            tup = (_normalize_value(row),)
        normalized.append(tup)
    return sorted(normalized, key=lambda t: tuple(_sort_key(v) for v in t))


def _normalize_value(value: Any) -> Any:
    # The API intentionally renders a one-cell result as a string. Convert
    # numeric strings back to numbers for comparison with DuckDB oracle rows.
    if isinstance(value, str) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.strip()):
        value = float(value)
    return round(value, 2) if isinstance(value, float) else value


def compare_results(oracle_res: List[tuple], api_res: List[tuple]) -> int:
    """Score correctness (0 / 15 / 30 / 45)."""
    if not oracle_res and not api_res:
        return 45
    if not api_res:
        return 0

    # Exact match (order-insensitive, already sorted)
    if len(oracle_res) == len(api_res) and all(
        len(o) == len(a) and all(_vals_close(ov, av) for ov, av in zip(o, a))
        for o, a in zip(oracle_res, api_res)
    ):
        return 45

    # Extra justification columns can earn partial credit only when each
    # oracle row is represented by one API row. Global value matching alone
    # could wrongly reward values attached to the wrong region or product.
    remaining_rows = list(api_res)
    matched_rows = 0
    for oracle_row in oracle_res:
        for i, api_row in enumerate(remaining_rows):
            values = list(api_row)
            if all(_pop_close(values, value) for value in oracle_row):
                matched_rows += 1
                remaining_rows.pop(i)
                break
    if matched_rows == len(oracle_res) and oracle_res:
        return 30

    # Some correct values still merit partial credit, but never full credit.
    api_vals = _flatten(api_res)
    oracle_vals = _flatten(oracle_res)

    matched = 0
    remaining = list(api_vals)
    for ov in oracle_vals:
        for i, av in enumerate(remaining):
            if _vals_close(ov, av):
                matched += 1
                remaining.pop(i)
                break

    if matched > 0:
        return 15  # partial
    return 0


def _pop_close(values: list, target: Any) -> bool:
    for i, value in enumerate(values):
        if _vals_close(target, value):
            values.pop(i)
            return True
    return False


def _flatten(rows: List[tuple]) -> list:
    return [v for row in rows for v in row]


def _sort_key(v: Any) -> tuple:
    """Return a (type_tag, value) tuple so mixed int/str lists can be sorted."""
    if isinstance(v, (int, float)):
        return (0, float(v))
    if v is None:
        return (2, "")
    return (1, str(v))


def _vals_close(a: Any, b: Any, tol: float = 0.015) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, abs_tol=tol)
    return str(a) == str(b)

# ---------------------------------------------------------------------------
# API caller
# ---------------------------------------------------------------------------

def call_api(question: str) -> Dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        try:
            resp = client.post(API_URL, json={"query": question})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f"  API error for '{question}': {exc}")
            return {
                "result": f"Error: {exc}",
                "confidence_score": 0.0,
                "explanation": "",
                "attempts": 0,
                "generated_sql": "",
            }

# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    gemini = GeminiPool()
    conn = setup_duckdb()

    with open(QUERIES_FILE, "r") as f:
        catalog = yaml.safe_load(f)["queries"]

    # Round 1: Run entire catalog
    round_name = "R1"
    target_queries = catalog

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M")
    trace_dir = TRACES_DIR / f"{timestamp}_{round_name}"
    trace_dir.mkdir(parents=True, exist_ok=True)

    # Feedback-log contamination control (§6.3)
    feedback_log_path = DATA_DIR / "feedback_log.csv"
    backup_feedback = trace_dir / "feedback_log.before.csv"

    if feedback_log_path.exists():
        shutil.copy(feedback_log_path, backup_feedback)
        with open(feedback_log_path, "r") as f:
            header = f.readline()
        with open(feedback_log_path, "w") as f:
            f.write(header)

    results: list[dict] = []
    RUNS = 1  # Use 1 run for fast initial baseline; bump to 3 for full eval

    logger.info(f"▶ Starting {round_name}: {len(target_queries)} queries × {RUNS} run(s)")

    for qi, q in enumerate(target_queries, 1):
        for run_idx in range(1, RUNS + 1):
            logger.info(f"  [{qi}/{len(target_queries)}] {q['id']} run {run_idx}: {q['question']}")

            # ---- Oracle result ----
            oracle_res: list[tuple] = []
            if "oracle_sql" in q:
                try:
                    oracle_res = conn.execute(q["oracle_sql"]).fetchall()
                except Exception as exc:
                    logger.error(f"    Oracle SQL error for {q['id']}: {exc}")
            oracle_norm = normalize_result(oracle_res)

            # ---- API call ----
            t0 = time.time()
            api_resp = call_api(q["question"])
            latency_ms = int((time.time() - t0) * 1000)

            api_result = api_resp.get("result", [])
            is_error = isinstance(api_result, str) and api_result.lower().startswith("error")
            api_norm = normalize_result(api_result) if not is_error else []

            # ---- Scoring ----
            scores: Dict[str, int] = {
                "executes": 0, "correct": 0, "confidence": 0,
                "explanation": 0, "sql_quality": 0, "efficiency": 0, "total": 0,
            }

            # 1. Executes
            if not is_error:
                scores["executes"] = 10

            # 2. Correct
            if not is_error and "expected_behaviour" not in q:
                scores["correct"] = compare_results(oracle_norm, api_norm)

            # 4 & 5. LLM judge
            conf = api_resp.get("confidence_score", 0)
            judge_res = gemini.judge(
                q["question"],
                api_resp.get("generated_sql", ""),
                api_resp.get("explanation", ""),
                result=api_result,
                confidence=conf,
                expected_behaviour=q.get("expected_behaviour", ""),
            )
            scores["explanation"] = judge_res.get("explanation_score", 0)
            scores["sql_quality"] = judge_res.get("sql_score", 0)
            if "expected_behaviour" in q and not is_error:
                scores["correct"] = judge_res.get("behaviour_score", 0)
                if scores["correct"] not in (0, 15, 30, 45):
                    scores["correct"] = 0

            # 3. Confidence calibration is based on actual or judged correctness.
            is_correct = scores["correct"] == 45
            if is_correct and "expected_behaviour" in q:
                # These cases deliberately include correct low-confidence
                # answers (missing year, undefined metric, read-only refusal).
                # The behaviour judge evaluates calibration against the case.
                scores["confidence"] = 15
            elif is_correct and conf >= 0.7:
                scores["confidence"] = 15
            elif not is_correct and conf <= 0.5:
                scores["confidence"] = 15
            elif not is_correct and conf >= 0.8:
                scores["confidence"] = 0
            else:
                scores["confidence"] = 7

            # 6. Efficiency
            attempts = api_resp.get("attempts", 1)
            scores["efficiency"] = {1: 5, 2: 3}.get(attempts, 0)

            scores["total"] = sum(v for k, v in scores.items() if k != "total")

            record = {
                "round": 0,
                "prompt_version": "v0",
                "query_id": q["id"],
                "run": run_idx,
                "split": q["split"],
                "question": q["question"],
                "request": {"query": q["question"]},
                "response": api_resp,
                "latency_ms": latency_ms,
                "oracle_result": [list(t) for t in oracle_norm],  # JSON-safe
                "scores": scores,
                "judge_notes": judge_res.get("notes", ""),
            }
            results.append(record)

            with open(trace_dir / "results.jsonl", "a") as f:
                f.write(json.dumps(record, default=str) + "\n")

            logger.info(f"    Score: {scores['total']}/100  (exec={scores['executes']} "
                        f"correct={scores['correct']} conf={scores['confidence']} "
                        f"expl={scores['explanation']} sql={scores['sql_quality']} "
                        f"eff={scores['efficiency']})")

            time.sleep(2)  # rate-limit spacing

    # ---- Summary ----
    _write_summary(results, target_queries, trace_dir, round_name)

    # Restore feedback log
    if backup_feedback.exists():
        shutil.copy(backup_feedback, feedback_log_path)

    logger.info(f"✅ {round_name} done — traces at {trace_dir}")


def _write_summary(results: list, queries: list, trace_dir: Path, round_name: str) -> None:
    """Write scores.csv and summary.md from the collected results."""
    score_cols = ["executes", "correct", "confidence", "explanation", "sql_quality", "efficiency", "total"]

    # Aggregate per query (median across runs)
    from statistics import median
    per_query: dict[str, dict] = {}
    for r in results:
        qid = r["query_id"]
        per_query.setdefault(qid, {c: [] for c in score_cols})
        for c in score_cols:
            per_query[qid][c].append(r["scores"][c])

    rows = []
    for qid in per_query:
        row = {"query_id": qid}
        for c in score_cols:
            row[c] = median(per_query[qid][c])
        rows.append(row)

    # scores.csv
    import csv
    with open(trace_dir / "scores.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["query_id"] + score_cols)
        w.writeheader()
        w.writerows(rows)

    # summary.md
    totals = [r["total"] for r in rows]
    mean_score = sum(totals) / len(totals) if totals else 0
    pass_rate = sum(1 for t in totals if t >= 80) / len(totals) * 100 if totals else 0
    correctness_rate = sum(1 for t in rows if t["correct"] >= 45) / len(rows) * 100 if rows else 0

    lines = [
        f"# Round {round_name} Summary\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean Score | {mean_score:.1f}/100 |",
        f"| Pass Rate (≥80) | {pass_rate:.0f}% |",
        f"| Correctness Rate | {correctness_rate:.0f}% |",
        f"| Queries Evaluated | {len(queries)} |",
        "",
        "## Per-Query Scores",
        "",
        "| Query | Exec | Correct | Conf | Expl | SQL | Eff | **Total** |",
        "|-------|------|---------|------|------|-----|-----|-----------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['query_id']} | {r['executes']:.0f} | {r['correct']:.0f} | "
            f"{r['confidence']:.0f} | {r['explanation']:.0f} | {r['sql_quality']:.0f} | "
            f"{r['efficiency']:.0f} | **{r['total']:.0f}** |"
        )
    lines.append("")

    with open(trace_dir / "summary.md", "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
