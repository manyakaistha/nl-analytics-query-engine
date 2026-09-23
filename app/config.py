"""
Application configuration — paths, environment variables, constants.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "static"
FEEDBACK_LOG = DATA_DIR / "feedback_log.csv"

# Environment
load_dotenv(PROJECT_ROOT / ".env")

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY_2") or os.getenv("GROQ_API_KEY", "")

# Models selectable from the UI — first entry is the default.
AVAILABLE_MODELS: list[str] = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]
GROQ_MODEL: str = os.getenv("GROQ_MODEL", AVAILABLE_MODELS[0])

# Engine tunables
MAX_SELF_CORRECT_ATTEMPTS: int = 3
FEEDBACK_CONTEXT_LIMIT: int = 20       # Max feedback entries to inject
GROQ_TEMPERATURE: float = 0.1          # Low temp → deterministic SQL
GROQ_MAX_TOKENS: int = 2048
QUERY_CACHE_MAX_ENTRIES: int = 128
QUERY_CACHE_MAX_ENTRY_BYTES: int = 256 * 1024
