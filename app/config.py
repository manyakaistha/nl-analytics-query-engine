"""Validated server configuration. Never log environment values."""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR = RAW_DATA_DIR / "processed"
STATIC_DIR = PROJECT_ROOT / "static"
FEEDBACK_LOG = DATA_DIR / "feedback_log.csv"  # legacy evaluation only
load_dotenv(PROJECT_ROOT / ".env", override=False)


def integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def valid_key(value: str | None) -> str:
    value = (value or "").strip()
    if not value or any(
        word in value.lower()
        for word in ("placeholder", "your_", "your-", "example", "changeme", "…", "...")
    ):
        return ""
    return value


GROQ_API_KEY = valid_key(os.getenv("GROQ_API_KEY")) or valid_key(
    os.getenv("GROQ_API_KEY_2")
)
AVAILABLE_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
GROQ_MODEL = os.getenv("GROQ_MODEL", AVAILABLE_MODELS[0])
if GROQ_MODEL not in AVAILABLE_MODELS:
    raise ValueError("GROQ_MODEL must be one of the supported model identifiers")
APP_ENV = os.getenv("APP_ENV", "development")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()
if LOG_LEVEL not in {"debug", "info", "warning", "error", "critical"}:
    raise ValueError("LOG_LEVEL is invalid")
MAX_SELF_CORRECT_ATTEMPTS = integer("MAX_SELF_CORRECT_ATTEMPTS", 2, 1, 3)
GROQ_TIMEOUT_SECONDS = integer("GROQ_TIMEOUT_SECONDS", 20, 1, 60)
GROQ_TEMPERATURE = 0.0
GROQ_MAX_TOKENS = 2048
QUERY_CACHE_MAX_ENTRIES = 64
QUERY_CACHE_MAX_ENTRY_BYTES = 128 * 1024
FEEDBACK_CONTEXT_LIMIT = 20
CLIENT_REQUESTS_PER_MINUTE = integer("CLIENT_REQUESTS_PER_MINUTE", 5, 1, 100)
GLOBAL_REQUESTS_PER_MINUTE = integer("GLOBAL_REQUESTS_PER_MINUTE", 30, 1, 1000)
MAX_CONCURRENT_REQUESTS = integer("MAX_CONCURRENT_REQUESTS", 2, 1, 4)
LLM_DAILY_REQUEST_BUDGET = integer("LLM_DAILY_REQUEST_BUDGET", 200, 0, 10000)
MAX_RESULT_ROWS = integer("MAX_RESULT_ROWS", 200, 1, 1000)
MAX_RESULT_BYTES = 128 * 1024
MAX_REQUEST_BYTES = 8192
SQL_TIMEOUT_SECONDS = integer("SQL_TIMEOUT_SECONDS", 3, 1, 10)
DUCKDB_MEMORY_MB = integer("DUCKDB_MEMORY_MB", 192, 64, 256)
