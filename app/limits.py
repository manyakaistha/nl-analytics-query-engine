"""Bounded, process-local admission control and UTC daily provider budget."""

import threading
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone
from app.config import (
    CLIENT_REQUESTS_PER_MINUTE,
    GLOBAL_REQUESTS_PER_MINUTE,
    LLM_DAILY_REQUEST_BUDGET,
    MAX_CONCURRENT_REQUESTS,
)


class UsageError(Exception):
    def __init__(self, message, status_code=429):
        self.status_code = status_code
        super().__init__(message)


class RateLimiter:
    def __init__(self):
        self.clients = OrderedDict()
        self.global_requests = deque()
        self.lock = threading.Lock()

    def check(self, client):
        now = time.monotonic()
        with self.lock:
            # Bound attacker-controlled client identities without resetting active buckets.
            for key in list(self.clients):
                bucket = self.clients[key]
                while bucket and bucket[0] <= now - 60:
                    bucket.popleft()
                if not bucket:
                    del self.clients[key]
            while self.global_requests and self.global_requests[0] <= now - 60:
                self.global_requests.popleft()
            bucket = self.clients.get(client, deque())
            if (
                len(bucket) >= CLIENT_REQUESTS_PER_MINUTE
                or len(self.global_requests) >= GLOBAL_REQUESTS_PER_MINUTE
                or (client not in self.clients and len(self.clients) >= 4096)
            ):
                raise UsageError(
                    "The demo is receiving too many requests. Please try again in one minute."
                )
            bucket.append(now)
            self.clients[client] = bucket
            self.global_requests.append(now)


class DailyBudget:
    def __init__(self):
        self.day = ""
        self.used = 0
        self.tokens = 0
        self.lock = threading.Lock()

    def consume(self):
        with self.lock:
            day = datetime.now(timezone.utc).date().isoformat()
            if day != self.day:
                self.day, self.used, self.tokens = day, 0, 0
            if self.used >= LLM_DAILY_REQUEST_BUDGET:
                raise UsageError(
                    "The demo has reached its daily AI request budget. Please return after 00:00 UTC."
                )
            self.used += 1

    def record_tokens(self, count):
        with self.lock:
            self.tokens += max(0, int(count or 0))


budget = DailyBudget()
provider_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
