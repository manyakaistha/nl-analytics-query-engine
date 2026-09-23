"""
Feedback log — read/write/append operations on feedback_log.csv.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.config import FEEDBACK_LOG, FEEDBACK_CONTEXT_LIMIT


# Schema
FIELDNAMES = [
    "timestamp",
    "query",
    "generated_sql",
    "status",
    "error_message",
    "user_feedback",
    "confidence_score",
]


# Write

def _ensure_log_exists() -> None:
    """Create the feedback log with a header row if it doesn't exist."""
    if not FEEDBACK_LOG.exists():
        FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(FEEDBACK_LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def append_entry(
    query: str,
    generated_sql: str,
    status: str,
    error_message: str = "",
    user_feedback: str = "",
    confidence_score: float = 0.0,
) -> None:
    """Append a single row to the feedback log."""
    _ensure_log_exists()
    with open(FEEDBACK_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "generated_sql": generated_sql,
            "status": status,
            "error_message": error_message,
            "user_feedback": user_feedback,
            "confidence_score": confidence_score,
        })


def update_user_feedback(query: str, generated_sql: str, feedback: str) -> bool:
    """
    Update the user_feedback field for a matching entry.
    Returns True if a match was found and updated.
    """
    _ensure_log_exists()
    rows = _read_all()

    updated = False
    for row in reversed(rows):  # Most recent first
        if row["query"] == query and row["generated_sql"] == generated_sql:
            row["user_feedback"] = feedback
            updated = True
            break

    if updated:
        _write_all(rows)
    return updated


# Read

def _read_all() -> list[dict]:
    """Read all rows from the feedback log."""
    _ensure_log_exists()
    with open(FEEDBACK_LOG, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_all(rows: list[dict]) -> None:
    """Overwrite the log with the given rows."""
    with open(FEEDBACK_LOG, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def get_recent_entries(limit: int | None = None) -> list[dict]:
    """Return the most recent N entries (default: FEEDBACK_CONTEXT_LIMIT)."""
    limit = limit or FEEDBACK_CONTEXT_LIMIT
    rows = _read_all()
    return rows[-limit:]


def build_feedback_context() -> str:
    """
    Summarize recent feedback without placing raw user or model text in the
    system prompt. Queries, SQL, and DuckDB errors are untrusted content.
    """
    entries = get_recent_entries()
    if not entries:
        return ""
    counts = Counter()
    for entry in entries:
        if entry.get("user_feedback") == "negative":
            counts["negative feedback"] += 1
        if entry.get("status") != "FAILED":
            continue
        error = entry.get("error_message", "").lower()
        if "read-only" in error or "permission" in error:
            counts["read-only violation"] += 1
        elif "binder" in error or "column" in error:
            counts["column error"] += 1
        elif "catalog" in error or "function" in error:
            counts["function error"] += 1
        elif "parser" in error or "syntax" in error:
            counts["syntax error"] += 1
        else:
            counts["other failure"] += 1

    if not counts:
        return ""
    return "Recent feedback counts (review the schema and dialect rules where relevant):\n" + "\n".join(
        f"  - {category}: {count}" for category, count in sorted(counts.items())
    )
