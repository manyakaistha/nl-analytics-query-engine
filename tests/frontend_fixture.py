"""Explicit offline browser fixture. Never use this entry point for deployment."""

import time
import json
from pathlib import Path
from unittest.mock import patch
import uvicorn
from app.models import LLMGeneratedOutput
from app.server import create_app
from scripts.benchmark import CASES


def generate_fixture(system_prompt, user_message, **kwargs):
    time.sleep(0.6)
    if user_message == "simulate timeout":
        raise TimeoutError("Offline simulated timeout")
    sql = next((sql for _, question, sql in CASES if question == user_message), None)
    if sql is None:
        examples = json.loads(
            (
                Path(__file__).resolve().parents[1] / "data/nl_queries_curated.json"
            ).read_text()
        )
        sql = next(
            (
                item["expected_logic"]
                for item in examples
                if item["query"] == user_message
            ),
            None,
        )
    if user_message == "Month-over-month revenue growth":
        sql = next(
            item["expected_logic"]
            for item in examples
            if item["query"] == "Monthly revenue with month-over-month change %"
        )
    if user_message == "Q1 target attainment by region":
        sql = "WITH s AS (SELECT region,SUM(revenue) AS revenue FROM sales_with_revenue GROUP BY region), t AS (SELECT region,SUM(target_revenue) AS target_revenue FROM targets GROUP BY region) SELECT t.region,s.revenue,t.target_revenue,100*s.revenue/t.target_revenue AS attainment_pct FROM t LEFT JOIN s ON t.region=s.region ORDER BY t.region"
    if sql is None:
        raise ValueError("No offline fixture for this question")
    return LLMGeneratedOutput(
        sql=sql,
        logic="Offline browser fixture: verified SQL executed against the real bundled dataset.",
        explanation="Not used.",
        confidence=0.8,
    )


if __name__ == "__main__":
    with patch("app.engine.generate_sql", side_effect=generate_fixture):
        uvicorn.run(create_app(), host="127.0.0.1", port=8001, log_level="warning")
