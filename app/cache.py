"""Small process-local LRU cache for successful analytics responses."""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from threading import Lock

from app.config import QUERY_CACHE_MAX_ENTRIES, QUERY_CACHE_MAX_ENTRY_BYTES
from app.models import QueryResponse


_entries: OrderedDict[str, QueryResponse] = OrderedDict()
_lock = Lock()
_expiry = {}


def make_cache_key(
    question: str,
    system_prompt: str,
    data_version: str,
    model: str,
    temperature: float,
    max_tokens: int,
    credential_scope: str = "server",
) -> str:
    """Whitespace-only normalization avoids merging different filter values."""
    payload = [
        " ".join(question.split()),
        system_prompt,
        data_version,
        model,
        temperature,
        max_tokens,
        credential_scope,
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def get_cached_response(key: str, question: str) -> QueryResponse | None:
    with _lock:
        saved = _entries.get(key)
        if saved is not None and _expiry.get(key, 0) < time.monotonic():
            _entries.pop(key, None)
            _expiry.pop(key, None)
            saved = None
        if saved is None:
            return None
        _entries.move_to_end(key)
        response = saved.model_copy(deep=True)
    response.query = question
    response.attempts = 0
    response.cache_hit = True
    return response


def cache_response(key: str, response: QueryResponse) -> None:
    """Store a copy, bounded by both entry count and individual response size."""
    if QUERY_CACHE_MAX_ENTRIES <= 0:
        return
    if len(response.model_dump_json().encode("utf-8")) > QUERY_CACHE_MAX_ENTRY_BYTES:
        return
    with _lock:
        _entries[key] = response.model_copy(deep=True)
        _expiry[key] = time.monotonic() + 900
        _entries.move_to_end(key)
        while len(_entries) > QUERY_CACHE_MAX_ENTRIES:
            old_key, _ = _entries.popitem(last=False)
            _expiry.pop(old_key, None)
