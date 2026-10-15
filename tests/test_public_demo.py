"""Offline acceptance tests: real DuckDB/data, mocked provider, no paid requests."""

import json
import threading
import time
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.database import execute_sql, get_profile
from app.engine import process_query, _self_correct_loop
from app.llm import _extract_json, generate_sql
from app.limits import DailyBudget, RateLimiter, UsageError
from app.models import LLMGeneratedOutput, QueryResponse
from app.server import create_app
from scripts.validate_data import validate_data
import app.cache as cache


def output(sql="SELECT SUM(revenue) AS total_revenue FROM sales_with_revenue"):
    return LLMGeneratedOutput(
        sql=sql,
        logic="Sum the supplied revenue.",
        explanation="Invented number 999999999",
        confidence=0.8,
    )


class DataTests(unittest.TestCase):
    def test_full_dataset_and_exact_revenue(self):
        profile = validate_data()
        self.assertEqual(
            (
                profile["rows"],
                profile["distinct_orders"],
                profile["distinct_customers"],
                profile["target_rows"],
            ),
            (50000, 33347, 8424, 9),
        )
        self.assertEqual(profile["date_range"], ["2024-01-01", "2024-03-31"])
        rows, _ = execute_sql(
            "SELECT SUM(revenue) AS revenue, SUM(profit) AS profit FROM sales_with_revenue"
        )
        self.assertEqual(rows[0]["revenue"], Decimal(profile["total_revenue"]))
        self.assertEqual(rows[0]["profit"], Decimal(profile["total_profit"]))

    def test_monthly_targets_and_repeated_customers(self):
        rows, _ = execute_sql(
            "WITH m AS (SELECT region,order_month,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY region,order_month) SELECT t.region,t.month,m.revenue,t.target_revenue FROM targets t LEFT JOIN m ON t.region=m.region AND t.month=m.order_month ORDER BY t.region,t.month"
        )
        profile = get_profile()
        self.assertEqual(len(rows), 9)
        for row in rows:
            self.assertEqual(
                row["revenue"],
                Decimal(profile["monthly_revenue"][row["region"] + "/" + row["month"]]),
            )
        rows, _ = execute_sql(
            "SELECT COUNT(*) AS n FROM (SELECT customer_id FROM sales_data GROUP BY customer_id HAVING COUNT(DISTINCT order_id)>1)"
        )
        self.assertEqual(rows[0]["n"], 6584)

    def test_stale_processed_data_is_refreshed_and_idempotent(self):
        from scripts import preprocess as prep

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            processed = root / "processed"
            raw.mkdir()
            for name in ("data_dictionary.json", "nl_queries_curated.json"):
                (raw / name).write_text("{}")
            for name in ("sales_data.csv", "targets.csv"):
                (raw / name).write_text("x\n1\n")
            with (
                patch.object(prep, "RAW_DATA_DIR", raw),
                patch.object(prep, "PROCESSED_DIR", processed),
            ):
                prep.ensure_processed_data()
                before = (processed / "sales_data.csv").stat().st_mtime_ns
                prep.ensure_processed_data()
                self.assertEqual(
                    before, (processed / "sales_data.csv").stat().st_mtime_ns
                )
                (raw / "sales_data.csv").write_text("x\n2\n")
                prep.ensure_processed_data()
                self.assertIn("2", (processed / "sales_data.csv").read_text())
                (processed / "sales_data.csv").write_text("stale")
                prep.ensure_processed_data()
                self.assertIn("2", (processed / "sales_data.csv").read_text())


class ConfigurationTests(unittest.TestCase):
    def test_placeholder_keys_and_primary_priority(self):
        from app.config import valid_key

        for value in ["", "your_groq_api_key", "PLACEHOLDER", "gsk_…"]:
            self.assertEqual(valid_key(value), "")
        import os, subprocess, sys

        env = {
            **os.environ,
            "GROQ_API_KEY": "fake-primary",
            "GROQ_API_KEY_2": "fake-secondary",
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.config import GROQ_API_KEY; assert GROQ_API_KEY == 'fake-primary'",
            ],
            env=env,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)
        env["GROQ_API_KEY"] = "your_groq_api_key"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.config import GROQ_API_KEY; assert GROQ_API_KEY == 'fake-secondary'",
            ],
            env=env,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)

    def test_curated_sql_examples_execute(self):
        examples = json.loads(Path("data/nl_queries_curated.json").read_text())
        for example in examples:
            with self.subTest(question=example["query"]):
                execute_sql(example["expected_logic"])


class SecurityTests(unittest.TestCase):
    def test_attack_catalog(self):
        attacks = [
            "INSERT INTO sales_data VALUES (1)",
            "UPDATE sales_data SET profit=0",
            "DELETE FROM sales_data",
            "DROP TABLE sales_data",
            "ALTER TABLE sales_data ADD x INT",
            "CREATE TABLE x AS SELECT 1",
            "TRUNCATE sales_data",
            "COPY sales_data TO '/tmp/leak.csv'",
            "ATTACH '/tmp/db'",
            "INSTALL httpfs",
            "LOAD httpfs",
            "SELECT 1; SELECT 2",
            "SELECT * FROM read_csv_auto('/etc/passwd')",
            "SELECT * FROM read_parquet('https://example.org/a')",
            "SELECT * FROM duckdb_settings()",
            "SELECT getenv('GROQ_API_KEY')",
            "SELECT * FROM information_schema.tables",
            "SELECT query('SELECT 1')",
            "WITH RECURSIVE r AS (SELECT 1 UNION ALL SELECT 1 FROM r) SELECT * FROM r",
            "WITH sales_data AS (SELECT * FROM private_data) SELECT * FROM sales_data",
            "SELECT repeat('x',1000000000)",
            "SELECT * FROM range(1000000000)",
            "SELECT * FROM '/etc/passwd'",
            "SELECT * FROM main.sales_data",
            "SELECT 1 INTO secret",
        ]
        for sql in attacks:
            with self.subTest(sql=sql), self.assertRaises(PermissionError):
                execute_sql(sql)

    def test_legitimate_analytics_and_column_binding(self):
        queries = [
            "SELECT region,SUM(profit) AS profit FROM sales_data GROUP BY region HAVING SUM(profit)>0 ORDER BY profit DESC",
            "WITH s AS (SELECT region,SUM(revenue) AS r FROM sales_with_revenue GROUP BY region) SELECT region,r,RANK() OVER(ORDER BY r DESC) AS ranking FROM s",
            "SELECT EXTRACT(month FROM order_date) AS month,COUNT(DISTINCT order_id) AS orders FROM sales_data GROUP BY month",
            "SELECT product_category,100*SUM(revenue)/SUM(SUM(revenue)) OVER() AS pct FROM sales_with_revenue GROUP BY product_category",
        ]
        for sql in queries:
            with self.subTest(sql=sql):
                self.assertTrue(execute_sql(sql)[0])
        with self.assertRaises(Exception):
            execute_sql("SELECT secret FROM sales_data")

    def test_results_are_bounded(self):
        with self.assertRaises(PermissionError):
            execute_sql("SELECT * FROM sales_data")
        self.assertEqual(len(execute_sql("SELECT * FROM sales_data LIMIT 200")[0]), 200)
        with (
            patch("app.database.MAX_RESULT_BYTES", 20),
            self.assertRaises(PermissionError),
        ):
            execute_sql("SELECT product_name FROM sales_data LIMIT 5")

    def test_real_interrupt_does_not_poison_next_query(self):
        start = time.perf_counter()
        with (
            patch("app.database.SQL_TIMEOUT_SECONDS", 0.03),
            self.assertRaises(Exception),
        ):
            execute_sql(
                "SELECT SUM(a.quantity*b.quantity*c.quantity) AS n FROM sales_data a CROSS JOIN sales_data b CROSS JOIN sales_data c"
            )
        self.assertLess(time.perf_counter() - start, 3)
        self.assertEqual(execute_sql("SELECT 1 AS n")[0], [{"n": 1}])

    def test_database_blocks_external_access_even_without_guard(self):
        from app.database import get_connection

        with self.assertRaises(Exception):
            get_connection().execute(
                "SELECT * FROM read_csv_auto('/etc/passwd')"
            ).fetchall()
        with self.assertRaises(Exception):
            get_connection().execute("SET enable_external_access=true")


class ProviderTests(unittest.TestCase):
    def setUp(self):
        cache._entries.clear()

    def test_json_fences_empty_and_sql_fences(self):
        self.assertEqual(
            _extract_json('```json\n{"sql":"```sql\\nSELECT 1\\n```"}\n```')["sql"],
            "SELECT 1",
        )
        for value in ["", None, "[]", "nonsense"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                _extract_json(value)

    def test_explanation_is_grounded_not_model_numbers(self):
        with patch("app.engine.generate_sql", return_value=output()):
            response = process_query("Total revenue", cache_scope="grounding")
        self.assertNotIn("999999999", response.explanation)
        self.assertIn("23341186.389", response.explanation)
        self.assertIn("groq", response.timings_ms)

    def test_unsafe_sql_does_not_retry(self):
        with patch(
            "app.engine.generate_sql", return_value=output("DROP TABLE sales_data")
        ) as generate:
            result = _self_correct_loop("drop", "prompt", "openai/gpt-oss-120b")
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result.error_code, "unsafe_sql")

    def test_timeout_and_secret_failure_are_sanitized(self):
        for exception in [
            TimeoutError("gsk_SECRET /private/server"),
            RuntimeError("gsk_SECRET"),
        ]:
            with patch("app.engine.generate_sql", side_effect=exception) as generate:
                result = _self_correct_loop("question", "prompt", "openai/gpt-oss-120b")
            self.assertEqual(generate.call_count, 1)
            self.assertNotIn("SECRET", result.error)

    def test_retryable_provider_error_is_bounded(self):
        class TemporaryError(Exception):
            status_code = 503

        with (
            patch(
                "app.engine.generate_sql",
                side_effect=[TemporaryError("secret"), output("SELECT 1 AS n")],
            ),
            patch("app.engine.time.sleep"),
        ):
            self.assertTrue(
                _self_correct_loop("q", "prompt", "openai/gpt-oss-120b").success
            )

    def test_daily_budget_and_reset(self):
        budget = DailyBudget()
        with patch("app.limits.LLM_DAILY_REQUEST_BUDGET", 1):
            budget.consume()
            with self.assertRaises(UsageError):
                budget.consume()
            budget.day = "2000-01-01"
            budget.consume()
            self.assertEqual(budget.used, 1)

    def test_budget_counts_each_actual_provider_call(self):
        budget = DailyBudget()
        client = MagicMock()
        client.chat.completions.create.return_value.choices[0].message.content = output(
            "SELECT 1"
        ).model_dump_json()
        with (
            patch("app.llm._get_client", return_value=client),
            patch("app.llm.budget", budget),
        ):
            generate_sql("prompt", "q")
        self.assertEqual(budget.used, 1)

    def test_missing_key(self):
        with patch("app.llm.GROQ_API_KEY", ""), self.assertRaises(UsageError):
            generate_sql("prompt", "q")

    def test_session_cache_and_dataset_version(self):
        with patch(
            "app.engine.generate_sql", return_value=output("SELECT 1 AS n")
        ) as generate:
            process_query("cache question", cache_scope="a")
            self.assertTrue(process_query("cache question", cache_scope="a").cache_hit)
            self.assertFalse(process_query("cache question", cache_scope="b").cache_hit)
            with patch("app.engine.get_data_version", return_value="changed"):
                self.assertFalse(
                    process_query("cache question", cache_scope="a").cache_hit
                )
        self.assertEqual(generate.call_count, 3)

    def test_duplicate_requests_share_generation(self):
        def delayed(**kwargs):
            time.sleep(0.05)
            return output("SELECT 1 AS n")

        with (
            patch("app.engine.generate_sql", side_effect=delayed) as generate,
            ThreadPoolExecutor(2) as pool,
        ):
            futures = [
                pool.submit(process_query, "duplicate question", cache_scope="same")
                for _ in range(2)
            ]
            responses = [future.result() for future in futures]
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(sum(r.cache_hit for r in responses), 1)


class APITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())
        cache._entries.clear()

    def test_page_models_health_history(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertTrue(self.client.get("/api/models").json()["models"])
        self.assertEqual(self.client.get("/healthz").json()["dataset_rows"], 50000)
        self.assertEqual(self.client.get("/api/history").status_code, 410)

    def test_browser_request_cache_and_model_change(self):
        with patch("app.engine.generate_sql", return_value=output()) as provider:
            first = self.client.post(
                "/api/query",
                json={"query": "Total revenue", "model": "openai/gpt-oss-120b"},
            )
            repeat = self.client.post(
                "/api/query",
                json={"query": " Total   revenue ", "model": "openai/gpt-oss-120b"},
            )
            changed = self.client.post(
                "/api/query",
                json={"query": "Total revenue", "model": "openai/gpt-oss-20b"},
            )
        self.assertEqual(
            [first.status_code, repeat.status_code, changed.status_code],
            [200, 200, 200],
        )
        self.assertFalse(first.json()["cache_hit"])
        self.assertTrue(repeat.json()["cache_hit"])
        self.assertEqual(repeat.json()["attempts"], 0)
        self.assertEqual(first.json()["result"], repeat.json()["result"])
        self.assertNotEqual(first.json()["feedback_id"], repeat.json()["feedback_id"])
        self.assertFalse(changed.json()["cache_hit"])
        self.assertEqual(provider.call_count, 2)

    def test_invalid_oversized_and_no_secret_echo(self):
        for body in [
            {"query": " "},
            {"query": ""},
            {"query": "x" * 1001},
            {"query": "a", "unknown": "secret"},
            {"query": "a", "model": "bad"},
        ]:
            self.assertEqual(self.client.post("/api/query", json=body).status_code, 422)
        self.assertEqual(
            self.client.post("/api/query", content="x" * 9000).status_code, 413
        )
        self.assertNotIn(
            "supersecret",
            self.client.post(
                "/api/query", json={"query": "a", "api_key": "supersecret"}
            ).text,
        )

    def test_feedback_is_session_isolated(self):
        with patch(
            "app.engine.generate_sql", return_value=output("SELECT 1 AS answer")
        ):
            response = self.client.post("/api/query", json={"query": "one"})
        self.assertEqual(response.status_code, 200)
        token = response.json()["feedback_id"]
        self.assertEqual(
            TestClient(create_app())
            .post("/api/feedback", json={"feedback_id": token, "feedback": "positive"})
            .status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/feedback", json={"feedback_id": token, "feedback": "positive"}
            ).status_code,
            200,
        )

    def test_client_and_global_limits_and_forwarded_header(self):
        with patch("app.engine.generate_sql", return_value=output("SELECT 1 AS n")):
            for i in range(5):
                self.assertEqual(
                    self.client.post(
                        "/api/query",
                        json={"query": "limit"},
                        headers={"X-Forwarded-For": str(i)},
                    ).status_code,
                    200,
                )
            self.assertEqual(
                self.client.post("/api/query", json={"query": "limit"}).status_code, 429
            )
        limiter = RateLimiter()
        with patch("app.limits.GLOBAL_REQUESTS_PER_MINUTE", 1):
            limiter.check("one")
            with self.assertRaises(UsageError):
                limiter.check("two")

    def test_empty_result_and_invalid_sql(self):
        with patch(
            "app.engine.generate_sql",
            return_value=output("SELECT * FROM sales_data WHERE quantity<0"),
        ):
            self.assertEqual(
                self.client.post("/api/query", json={"query": "empty"}).json()[
                    "result"
                ],
                "No results found.",
            )
        with patch(
            "app.engine.generate_sql", return_value=output("DELETE FROM sales_data")
        ):
            self.assertEqual(
                self.client.post("/api/query", json={"query": "bad"}).status_code, 422
            )

    def test_provider_failures_have_correct_status(self):
        with patch("app.llm.GROQ_API_KEY", ""):
            self.assertEqual(
                self.client.post(
                    "/api/query", json={"query": "missing key"}
                ).status_code,
                503,
            )

        class RateLimit(Exception):
            status_code = 429

        with patch("app.engine.generate_sql", side_effect=RateLimit("gsk_secret")):
            response = self.client.post("/api/query", json={"query": "quota"})
        self.assertEqual(response.status_code, 429)
        self.assertNotIn("gsk_secret", response.text)

    def test_actual_daily_budget_returns_429_without_calling_provider(self):
        client = MagicMock()
        with (
            patch("app.llm._get_client", return_value=client),
            patch("app.llm.budget", DailyBudget()),
            patch("app.limits.LLM_DAILY_REQUEST_BUDGET", 0),
        ):
            response = self.client.post("/api/query", json={"query": "daily budget"})
        self.assertEqual(response.status_code, 429)
        client.chat.completions.create.assert_not_called()

    def test_feedback_expiry(self):
        from app.feedback import issue_receipt, record_feedback

        token = issue_receipt("test-session")
        with patch("app.feedback.time.monotonic", return_value=time.monotonic() + 901):
            self.assertFalse(record_feedback(token, "test-session", "positive"))

    def test_concurrency_overload(self):
        entered, release = threading.Event(), threading.Event()

        def wait(*args, **kwargs):
            entered.set()
            release.wait(3)
            return QueryResponse(
                query="one",
                generated_sql="SELECT 1",
                generated_logic="",
                result="1",
                confidence_score=0.5,
                explanation="one",
            )

        with (
            TestClient(create_app()) as client,
            patch("app.server.MAX_CONCURRENT_REQUESTS", 1),
            patch("app.server.process_query", side_effect=wait),
            ThreadPoolExecutor(1) as pool,
        ):
            future = pool.submit(client.post, "/api/query", json={"query": "slow"})
            self.assertTrue(entered.wait(2))
            self.assertEqual(
                client.post("/api/query", json={"query": "busy"}).status_code, 429
            )
            release.set()
            self.assertEqual(future.result().status_code, 200)


if __name__ == "__main__":
    unittest.main()
