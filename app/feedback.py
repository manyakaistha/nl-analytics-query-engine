"""Ephemeral feedback receipts. No query text, SQL, IPs, or global history."""

import secrets
import time
from collections import OrderedDict, Counter
from threading import Lock

_lock = Lock()
_receipts = OrderedDict()
_counts = Counter()


def issue_receipt(session: str) -> str:
    with _lock:
        now = time.monotonic()
        for key in list(_receipts):
            if _receipts[key]["expires"] < now:
                del _receipts[key]
        while len(_receipts) >= 256:
            _receipts.popitem(last=False)
        token = secrets.token_urlsafe(24)
        _receipts[token] = {"session": session, "expires": now + 900, "feedback": None}
        return token


def record_feedback(token: str, session: str, feedback: str) -> bool:
    with _lock:
        item = _receipts.get(token)
        if not item or item["session"] != session or item["expires"] < time.monotonic():
            return False
        if item["feedback"]:
            _counts[item["feedback"]] -= 1
        item["feedback"] = feedback
        _counts[feedback] += 1
        return True


def append_entry(**kwargs):
    """Compatibility hook: requests are deliberately no longer persisted."""


def get_recent_entries(limit=None):
    return []


def build_feedback_context():
    # Kept for existing regression/evaluation imports; never inject raw content.
    entries = get_recent_entries()
    counts = Counter()
    for entry in entries:
        error = entry.get("error_message", "").lower()
        if "column" in error or "binder" in error:
            counts["column error"] += 1
    return "\n".join(f"{key}: {value}" for key, value in counts.items())
