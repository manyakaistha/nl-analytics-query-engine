"""Reproducible offline SQL/API benchmark; no provider requests are made."""

import argparse
import json
import platform
import resource
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import execute_sql, get_profile, get_connection
from app.models import LLMGeneratedOutput
from app.server import create_app
from app.prompts import build_system_prompt
import app.cache as cache

CASES = [
    (
        "total_revenue",
        "What is the total revenue?",
        "SELECT SUM(revenue) AS total_revenue FROM sales_with_revenue",
    ),
    (
        "regional_revenue",
        "Which region generated the most revenue?",
        "SELECT region,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY region ORDER BY revenue DESC",
    ),
    (
        "category_profit",
        "Which product category is most profitable?",
        "SELECT product_category,SUM(profit) AS profit FROM sales_data GROUP BY product_category ORDER BY profit DESC",
    ),
    (
        "category_revenue",
        "Revenue by category",
        "SELECT product_category,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY product_category ORDER BY revenue DESC",
    ),
    (
        "monthly_revenue",
        "Show monthly revenue by region.",
        "SELECT order_month,region,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY order_month,region ORDER BY order_month,region",
    ),
    (
        "aov",
        "What is the average order value?",
        "SELECT SUM(revenue)/COUNT(DISTINCT order_id) AS average_order_value FROM sales_with_revenue",
    ),
    (
        "top_customers",
        "Top 10 customers by revenue",
        "SELECT customer_id,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY customer_id ORDER BY revenue DESC,customer_id LIMIT 10",
    ),
    (
        "targets",
        "How does revenue compare with monthly targets?",
        "WITH m AS (SELECT region,order_month,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY region,order_month) SELECT t.region,t.month,COALESCE(m.revenue,0) AS actual_revenue,t.target_revenue,100*COALESCE(m.revenue,0)/t.target_revenue AS attainment_pct FROM targets t LEFT JOIN m ON t.region=m.region AND t.month=m.order_month ORDER BY t.region,t.month",
    ),
    (
        "products",
        "What are the top 10 products by revenue?",
        "SELECT product_name,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY product_name ORDER BY revenue DESC LIMIT 10",
    ),
    (
        "segments",
        "Which customer segment generates the most sales?",
        "SELECT customer_segment,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY customer_segment ORDER BY revenue DESC",
    ),
    (
        "repeat_customers",
        "Which top 50 customers placed multiple orders?",
        "SELECT customer_id,COUNT(DISTINCT order_id) AS orders,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY customer_id HAVING COUNT(DISTINCT order_id)>1 ORDER BY revenue DESC,customer_id LIMIT 50",
    ),
    (
        "profit_margin",
        "Profit margins by region",
        "SELECT region,SUM(profit) AS profit,100*SUM(profit)/NULLIF(SUM(revenue),0) AS margin_pct FROM sales_with_revenue GROUP BY region ORDER BY region",
    ),
]


def summary(values):
    values = sorted(values)
    return {
        "median_ms": round(statistics.median(values), 3),
        "p90_ms": round(
            values[max(0, __import__("math").ceil(0.9 * len(values)) - 1)], 3
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error("--runs must be 1..20")
    start = time.perf_counter()
    get_connection()
    startup = (time.perf_counter() - start) * 1000
    records = []
    # Only this isolated offline process raises admission thresholds to measure repeated calls.
    with (
        TestClient(create_app()) as client,
        patch("app.limits.CLIENT_REQUESTS_PER_MINUTE", 10000),
        patch("app.limits.GLOBAL_REQUESTS_PER_MINUTE", 10000),
    ):
        for name, question, sql in CASES:
            sql_times = []
            miss_times = []
            hit_times = []
            groq_times = []
            rows, columns = execute_sql(sql)
            for _ in range(args.runs):
                start = time.perf_counter()
                execute_sql(sql)
                sql_times.append((time.perf_counter() - start) * 1000)
                cache._entries.clear()
                completion = LLMGeneratedOutput(
                    sql=sql,
                    logic="Offline oracle SQL fixture.",
                    explanation="Not used: explanations are grounded in result rows.",
                    confidence=1,
                )
                with patch(
                    "app.engine.generate_sql", return_value=completion
                ) as provider:
                    start = time.perf_counter()
                    miss = client.post("/api/query", json={"query": question})
                    miss_times.append((time.perf_counter() - start) * 1000)
                    start = time.perf_counter()
                    hit = client.post("/api/query", json={"query": question})
                    hit_times.append((time.perf_counter() - start) * 1000)
                    assert miss.status_code == hit.status_code == 200, (
                        name,
                        miss.text,
                        hit.text,
                    )
                    assert hit.json()["cache_hit"] and provider.call_count == 1
                    assert miss.json()["result"] == hit.json()["result"]
                    groq_times.append(miss.json()["timings_ms"]["groq"])
            records.append(
                {
                    "case": name,
                    "question": question,
                    "oracle_sql": sql,
                    "oracle_result": rows,
                    "sql": summary(sql_times),
                    "mocked_api_cache_miss": summary(miss_times),
                    "mocked_api_cache_hit": summary(hit_times),
                    "mocked_groq": summary(groq_times),
                }
            )
    path = (
        Path("docs/benchmarks")
        / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-offline.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024**2 if platform.system() == "Darwin" else 1024
    )
    result = {
        "mode": "OFFLINE / MOCKED GROQ; no live generation accuracy or latency measured",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "runs_per_case": args.runs,
        "database_startup_ms": round(startup, 3),
        "process_peak_rss_mib": round(rss, 2),
        "prompt_characters": len(build_system_prompt()),
        "dataset": get_profile(),
        "cases": records,
    }
    path.write_text(json.dumps(result, default=str, indent=2) + "\n")
    print(path)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"cases", "dataset"}}, indent=2
        )
    )
    print(
        "Median across case medians:",
        json.dumps(
            {
                metric: summary([r[metric]["median_ms"] for r in records])
                for metric in ["sql", "mocked_api_cache_miss", "mocked_api_cache_hit"]
            }
        ),
    )


if __name__ == "__main__":
    main()
