"""Bounded Groq calls; SDK retries are disabled so every call consumes our budget."""

import json
import re
import logging
import time
from threading import Lock
from contextvars import ContextVar
from groq import Groq
from app.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    GROQ_TEMPERATURE,
    GROQ_MAX_TOKENS,
    GROQ_TIMEOUT_SECONDS,
)
from app.limits import budget, provider_slots, UsageError
from app.models import LLMGeneratedOutput

_client = None
_client_lock = Lock()
call_timings = ContextVar("llm_call_timings", default=None)


def _get_client():
    global _client
    if not GROQ_API_KEY:
        raise UsageError(
            "AI is not configured yet. The demo owner needs to set GROQ_API_KEY.", 503
        )
    with _client_lock:
        if _client is None:
            _client = Groq(
                api_key=GROQ_API_KEY, timeout=GROQ_TIMEOUT_SECONDS, max_retries=0
            )
    return _client


def close_client():
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _extract_json(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 24000:
        raise ValueError("Empty or oversized model response")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise ValueError("Malformed model response") from None
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(value, dict):
        raise ValueError("Model response must be an object")
    if isinstance(value.get("sql"), str):
        value["sql"] = re.sub(r"^```(?:sql)?\s*|\s*```$", "", value["sql"].strip())
    return value


def generate_sql(system_prompt, user_message, model=GROQ_MODEL, api_key=None):
    client = (
        Groq(api_key=api_key, timeout=GROQ_TIMEOUT_SECONDS, max_retries=0)
        if api_key
        else _get_client()
    )
    if not provider_slots.acquire(blocking=False):
        if api_key:
            client.close()
        raise UsageError("The demo is busy. Please try again shortly.")
    try:
        budget.consume()
        start = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=GROQ_TEMPERATURE,
            max_tokens=GROQ_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
        provider_ms = (time.perf_counter() - start) * 1000
        if response.usage:
            budget.record_tokens(response.usage.total_tokens)
            logging.getLogger(__name__).info(
                "Groq completion model=%s tokens=%s elapsed_ms=%.1f",
                model,
                response.usage.total_tokens,
                (time.perf_counter() - start) * 1000,
            )
        if not response.choices or response.choices[0].finish_reason == "length":
            raise ValueError("Incomplete model response")
        parsing_start = time.perf_counter()
        output = LLMGeneratedOutput(
            **_extract_json(response.choices[0].message.content)
        )
        call_timings.set(
            {
                "groq_request": round(provider_ms, 3),
                "model_parsing": round((time.perf_counter() - parsing_start) * 1000, 3),
            }
        )
        return output
    finally:
        provider_slots.release()
        if api_key:
            client.close()
