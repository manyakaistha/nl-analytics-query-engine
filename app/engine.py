"""
Query engine — orchestrates the NL → SQL → DuckDB → result pipeline
with a self-correction retry loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.cache import cache_response, get_cached_response, make_cache_key
from app.config import (
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    MAX_SELF_CORRECT_ATTEMPTS,
)
from app.database import execute_sql, get_data_version
from app.feedback import append_entry, build_feedback_context
from app.llm import generate_sql
from app.models import LLMGeneratedOutput, QueryResponse
from app.prompts import build_system_prompt, build_retry_user_message


# Internal result wrapper
@dataclass
class _AttemptResult:
    """Tracks the outcome of a single generate-execute attempt."""
    success: bool = False
    llm_output: LLMGeneratedOutput | None = None
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    error: str = ""


# Core pipeline

def process_query(user_query: str) -> QueryResponse:
    """Run the pipeline and stamp the server-side response time."""
    start = time.perf_counter()
    response = _run_pipeline(user_query)
    response.response_time_ms = int((time.perf_counter() - start) * 1000)
    return response


def _run_pipeline(user_query: str) -> QueryResponse:
    """
    End-to-end pipeline:
      1. Build system prompt with feedback context
      2. Reuse a successful response when the question, prompt, model, and
         loaded data snapshot match
      3. Otherwise run the self-correction loop (up to N attempts)
      4. Log the outcome and return a structured QueryResponse
    """
    feedback_ctx = build_feedback_context()
    system_prompt = build_system_prompt(feedback_context=feedback_ctx)
    cache_key = make_cache_key(
        question=user_query,
        system_prompt=system_prompt,
        data_version=get_data_version(),
        model=GROQ_MODEL,
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
    )
    cached = get_cached_response(cache_key, user_query)
    if cached is not None:
        append_entry(
            query=user_query,
            generated_sql=cached.generated_sql,
            status="SUCCESS",
            confidence_score=cached.confidence_score,
        )
        return cached

    result = _self_correct_loop(
        user_query=user_query,
        system_prompt=system_prompt,
    )

    # Build the response
    if result.success and result.llm_output is not None:
        # Format result: single scalar vs table
        formatted_result = _format_result(result.rows, result.columns)

        response = QueryResponse(
            query=user_query,
            generated_sql=result.llm_output.sql,
            generated_logic=result.llm_output.logic,
            result=formatted_result,
            confidence_score=result.llm_output.confidence,
            explanation=result.llm_output.explanation,
            attempts=result.attempt_number,
        )

        # Log success
        append_entry(
            query=user_query,
            generated_sql=result.llm_output.sql,
            status="SUCCESS",
            confidence_score=result.llm_output.confidence,
        )
        cache_response(cache_key, response)
    else:
        # All attempts failed
        sql_used = result.llm_output.sql if result.llm_output else ""
        explanation = (
            "The Groq model is temporarily at its rate limit. Please retry "
            "after the quota resets."
            if result.error.startswith("Groq rate limit")
            else (
                "I was unable to generate a valid SQL query for your question "
                "after multiple attempts. Please try rephrasing your question "
                "or check the error details."
            )
        )
        response = QueryResponse(
            query=user_query,
            generated_sql=sql_used,
            generated_logic="Query generation failed.",
            result=f"Error: {result.error}",
            confidence_score=0.0,
            explanation=explanation,
            attempts=result.attempt_number,
        )

        # Log failure
        append_entry(
            query=user_query,
            generated_sql=sql_used,
            status="FAILED",
            error_message=result.error,
            confidence_score=0.0,
        )

    return response


# Self-correction loop

@dataclass
class _LoopResult(_AttemptResult):
    attempt_number: int = 1


def _self_correct_loop(
    user_query: str,
    system_prompt: str,
) -> _LoopResult:
    """
    Try up to MAX_SELF_CORRECT_ATTEMPTS times to generate valid SQL.

    On each failure, the error message is fed back into the LLM prompt
    so it can self-correct.
    """
    prior_errors: list[tuple[str, str]] = []  # (failed_sql, error_msg)

    for attempt in range(1, MAX_SELF_CORRECT_ATTEMPTS + 1):
        result = _LoopResult(attempt_number=attempt)

        # --- Step 1: Generate SQL ---
        try:
            if attempt == 1:
                user_message = user_query
            else:
                last_sql, last_err = prior_errors[-1]
                user_message = build_retry_user_message(
                    original_query=user_query,
                    failed_sql=last_sql,
                    error_message=last_err,
                    attempt=attempt,
                )

            llm_output = generate_sql(
                system_prompt=system_prompt,
                user_message=user_message,
            )
            result.llm_output = llm_output

        except Exception as exc:
            if getattr(exc, "status_code", None) == 429:
                result.error = "Groq rate limit reached. Please retry after the quota resets."
                return result
            result.error = f"LLM generation error: {exc}"
            print(f"  [Attempt {attempt}] LLM error: {exc}")
            prior_errors.append(("", str(exc)))
            continue

        # --- Step 2: Execute SQL ---
        try:
            rows, columns = execute_sql(llm_output.sql)
            result.success = True
            result.rows = rows
            result.columns = columns
            print(f"  [Attempt {attempt}] ✓ SQL executed — {len(rows)} rows")
            return result

        except Exception as exc:
            error_msg = str(exc)
            result.error = error_msg
            prior_errors.append((llm_output.sql, error_msg))
            print(f"  [Attempt {attempt}] ✗ SQL error: {error_msg}")

    # All attempts exhausted
    final = _LoopResult(attempt_number=MAX_SELF_CORRECT_ATTEMPTS)
    if prior_errors:
        last_sql, last_err = prior_errors[-1]
        final.error = last_err
        # Keep the last LLM output for reporting
        final.llm_output = result.llm_output
    return final


# Result formatting

def _format_result(
    rows: list[dict],
    columns: list[str],
) -> list[dict] | str:
    """
    Format DuckDB results for the frontend:
      - 0 rows → descriptive string
      - 1 row, 1 column → scalar string
      - Otherwise → list of dicts (rendered as table in the frontend)
    """
    if not rows:
        return "No results found."

    if len(rows) == 1 and len(columns) == 1:
        # Single scalar value
        val = rows[0][columns[0]]
        return str(val)

    # Coerce non-serializable types (Decimal, date, etc.) to strings
    clean_rows: list[dict] = []
    for row in rows:
        clean_row = {}
        for k, v in row.items():
            try:
                # Test JSON serialization
                import json
                json.dumps(v)
                clean_row[k] = v
            except (TypeError, ValueError):
                clean_row[k] = str(v)
        clean_rows.append(clean_row)

    return clean_rows
