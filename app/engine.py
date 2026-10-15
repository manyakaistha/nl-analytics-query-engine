"""
Query engine — orchestrates the NL → SQL → DuckDB → result pipeline
with a self-correction retry loop.
"""

from __future__ import annotations

import time
import hashlib
import threading
import duckdb
from app.limits import UsageError
from app.config import MAX_RESULT_ROWS
from dataclasses import dataclass, field

from app.cache import cache_response, get_cached_response, make_cache_key
from app.config import (
    AVAILABLE_MODELS,
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    MAX_SELF_CORRECT_ATTEMPTS,
)
from app.database import execute_sql, get_data_version
from app.feedback import append_entry
from app.llm import generate_sql, call_timings
from app.models import LLMGeneratedOutput, QueryResponse
from app.prompts import build_system_prompt, build_retry_user_message


@dataclass
class _AttemptResult:
    """Tracks the outcome of a single generate-execute attempt."""

    success: bool = False
    llm_output: LLMGeneratedOutput | None = None
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    error: str = ""
    error_code: str | None = None
    timings_ms: dict = field(default_factory=dict)


def process_query(
    user_query: str,
    model: str | None = None,
    api_key: str | None = None,
    cache_scope: str = "local",
) -> QueryResponse:
    """Run the pipeline and stamp the server-side response time."""
    resolved_model = model if model in AVAILABLE_MODELS else GROQ_MODEL
    start = time.perf_counter()
    with _query_locks[
        int(
            hashlib.sha256(
                (cache_scope + " ".join(user_query.split())).encode()
            ).hexdigest(),
            16,
        )
        % len(_query_locks)
    ]:
        response = _run_pipeline(
            user_query,
            resolved_model,
            api_key.strip() if api_key else None,
            cache_scope,
        )
    response.response_time_ms = int((time.perf_counter() - start) * 1000)
    return response


_query_locks = [threading.Lock() for _ in range(32)]


def _run_pipeline(
    user_query: str, model: str, api_key: str | None = None, cache_scope: str = "local"
) -> QueryResponse:
    """
    End-to-end pipeline:
      1. Build the compact dataset-grounded system prompt
      2. Reuse a successful response when the question, prompt, model, and
         loaded data snapshot match
      3. Otherwise run the self-correction loop (up to N attempts)
      4. Return a structured response without persisting query history
    """
    prompt_start = time.perf_counter()
    feedback_ctx = ""
    system_prompt = build_system_prompt(feedback_context=feedback_ctx)
    cache_key = make_cache_key(
        question=user_query,
        system_prompt=system_prompt,
        data_version=get_data_version(),
        model=model,
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
        credential_scope=cache_scope
        + (
            "user:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            if api_key
            else "server"
        ),
    )
    prompt_ms = (time.perf_counter() - prompt_start) * 1000
    cached = get_cached_response(cache_key, user_query)
    if cached is not None:
        append_entry(
            query=user_query,
            generated_sql=cached.generated_sql,
            status="SUCCESS",
            confidence_score=cached.confidence_score,
        )
        cached.timings_ms = {"prompt": round(prompt_ms, 3), "groq": 0, "sql": 0}
        return cached

    result = _self_correct_loop(
        user_query=user_query,
        system_prompt=system_prompt,
        model=model,
        api_key=api_key,
    )

    if result.success and result.llm_output is not None:
        formatted_result = _format_result(result.rows, result.columns)

        response = QueryResponse(
            query=user_query,
            generated_sql=result.llm_output.sql,
            generated_logic=result.llm_output.logic,
            result=formatted_result,
            confidence_score=result.llm_output.confidence,
            explanation=_grounded_explanation(result.rows, result.columns),
            timings_ms={**result.timings_ms, "prompt": round(prompt_ms, 3)},
            dataset_version=get_data_version(),
            row_limit=MAX_RESULT_ROWS,
            attempts=result.attempt_number,
            model=model,
        )
        append_entry(
            query=user_query,
            generated_sql=result.llm_output.sql,
            status="SUCCESS",
            confidence_score=result.llm_output.confidence,
        )
        cache_response(cache_key, response)
    else:
        sql_used = result.llm_output.sql if result.llm_output else ""
        if result.error.startswith("Groq rate limit"):
            explanation = "The Groq model is temporarily at its rate limit. Please retry after the quota resets."
        elif result.error.startswith("Groq rejected"):
            explanation = (
                "Check the Groq API key and whether it can access the selected model."
            )
        else:
            explanation = (
                "I was unable to generate a valid SQL query for your question "
                "after multiple attempts. Please try rephrasing your question "
                "or check the error details."
            )
        response = QueryResponse(
            query=user_query,
            generated_sql=sql_used,
            generated_logic="Query generation failed.",
            result=f"Error: {result.error}",
            error_code=result.error_code or "generation_failed",
            timings_ms=result.timings_ms,
            confidence_score=0.0,
            explanation=explanation,
            attempts=result.attempt_number,
            model=model,
        )
        append_entry(
            query=user_query,
            generated_sql=sql_used,
            status="FAILED",
            error_message=result.error,
            confidence_score=0.0,
        )

    return response


@dataclass
class _LoopResult(_AttemptResult):
    attempt_number: int = 1


def _self_correct_loop(
    user_query: str,
    system_prompt: str,
    model: str,
    api_key: str | None = None,
) -> _LoopResult:
    """
    Try up to MAX_SELF_CORRECT_ATTEMPTS times to generate valid SQL.

    On each failure, the error message is fed back into the LLM prompt
    so it can self-correct.
    """
    prior_errors = []
    timings = {"groq": 0.0, "sql": 0.0}
    for attempt in range(1, MAX_SELF_CORRECT_ATTEMPTS + 1):
        result = _LoopResult(attempt_number=attempt, timings_ms=timings)
        user_message = (
            user_query
            if not prior_errors
            else build_retry_user_message(
                user_query, prior_errors[-1][0], prior_errors[-1][1], attempt
            )
        )
        start = time.perf_counter()
        try:
            call_timings.set(None)
            output = generate_sql(
                system_prompt=system_prompt,
                user_message=user_message,
                model=model,
                api_key=api_key,
            )
            result.llm_output = output
        except Exception as exc:
            timings["groq"] += round((time.perf_counter() - start) * 1000, 3)
            status = getattr(exc, "status_code", None)
            if isinstance(exc, UsageError):
                result.error, result.error_code = (
                    str(exc),
                    "budget" if status == 429 else "unavailable",
                )
                return result
            if status == 429:
                result.error, result.error_code = (
                    "Groq rate limit reached. Please try again later.",
                    "provider_rate_limit",
                )
                return result
            if status in (400, 401, 403, 404):
                result.error, result.error_code = (
                    "Groq rejected the request or model access. Please contact the demo owner.",
                    "provider_access",
                )
                return result
            retryable = status in (500, 502, 503, 504) or isinstance(exc, (ValueError,))
            result.error, result.error_code = (
                "AI service is unavailable or returned an invalid response. Please retry shortly.",
                "provider_failure",
            )
            if not retryable or attempt == MAX_SELF_CORRECT_ATTEMPTS:
                return result
            prior_errors.append(
                ("", "Invalid model response; return the required JSON format.")
            )
            time.sleep(0.25 * attempt)
            continue
        timings["groq"] += round((time.perf_counter() - start) * 1000, 3)
        for name, value in (call_timings.get() or {}).items():
            timings[name] = timings.get(name, 0) + value
        start = time.perf_counter()
        try:
            result.rows, result.columns = execute_sql(output.sql, timings=timings)
            result.success = True
            return result
        except (duckdb.InterruptException, duckdb.OutOfMemoryException):
            result.error, result.error_code = (
                "The query exceeded the demo's time or memory limit. Please narrow your question.",
                "resource_limit",
            )
            return result
        except PermissionError:
            result.error, result.error_code = (
                "The query exceeded the demo safety limits. Please narrow or rephrase your question.",
                "unsafe_sql",
            )
            return result
        except Exception:
            result.error, result.error_code = (
                "The query could not run within the available schema and resources. Please rephrase your question.",
                "sql_failed",
            )
            prior_errors.append(
                (
                    output.sql,
                    "SQL failed: check column names, DuckDB syntax, grouping, and resource limits.",
                )
            )
        finally:
            timings["sql"] += round((time.perf_counter() - start) * 1000, 3)
    return result


def _grounded_explanation(rows, columns):
    if not rows:
        return "No matching records were found in the synthetic dataset."
    if len(rows) == 1 and len(columns) == 1:
        return f"{columns[0].replace('_', ' ')}: {rows[0][columns[0]]}. Based on the synthetic January–March 2024 dataset."
    if columns == ["message"]:
        return str(rows[0]["message"])
    return f"Returned {len(rows)} rows from the synthetic January–March 2024 dataset. The SQL below defines the calculation; amounts use the dataset's unspecified currency unit."


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
        val = rows[0][columns[0]]
        return str(val)

    # Coerce non-serializable types (Decimal, date, etc.) to strings
    clean_rows: list[dict] = []
    for row in rows:
        clean_row = {}
        for k, v in row.items():
            try:
                import json

                json.dumps(v)
                clean_row[k] = v
            except (TypeError, ValueError):
                clean_row[k] = str(v)
        clean_rows.append(clean_row)

    return clean_rows
