"""Tests for Redis-backed rate limiting."""

import time

from app.core import rate_limit


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.expiry = {}

    def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key, ttl):
        self.expiry[key] = int(time.time()) + ttl


def test_rate_limit_trips(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rate_limit, "get_redis", lambda: fake)
    client_id = "api_key:test"

    # Exhaust limit
    for _ in range(rate_limit.RATE_LIMIT_MAX_REQUESTS + 1):
        limited, _ = rate_limit.is_rate_limited(client_id, "/api/v1/ingest/usage")
    assert limited is True
