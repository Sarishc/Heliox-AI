"""Small in-memory Redis stand-in for rate-limit and login-protection tests.

Implements only the commands those modules use, with real TTL semantics driven
by an adjustable clock (``advance``), so tests are deterministic.
"""

import time


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.expires_at = {}
        self.offset = 0.0
        self.fail = False  # set True to simulate an outage

    # clock
    def now(self):
        return time.time() + self.offset

    def advance(self, seconds):
        self.offset += seconds

    def _check(self):
        if self.fail:
            raise ConnectionError("fake redis down")

    def _purge(self, key):
        exp = self.expires_at.get(key)
        if exp is not None and exp <= self.now():
            self.store.pop(key, None)
            self.expires_at.pop(key, None)

    # commands
    def ping(self):
        self._check()
        return True

    def get(self, key):
        self._check()
        self._purge(key)
        value = self.store.get(key)
        return None if value is None else str(value)

    def incr(self, key):
        self._check()
        self._purge(key)
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def expire(self, key, ttl):
        self._check()
        self._purge(key)
        if key not in self.store:
            return False
        self.expires_at[key] = self.now() + ttl
        return True

    def setex(self, key, ttl, value):
        self._check()
        self.store[key] = value
        self.expires_at[key] = self.now() + ttl
        return True

    def ttl(self, key):
        self._check()
        self._purge(key)
        if key not in self.store:
            return -2
        exp = self.expires_at.get(key)
        return -1 if exp is None else max(1, int(exp - self.now() + 0.999))

    def exists(self, *keys):
        self._check()
        count = 0
        for key in keys:
            self._purge(key)
            count += key in self.store
        return count

    def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            removed += self.store.pop(key, None) is not None
            self.expires_at.pop(key, None)
        return removed

    def keys_matching(self, fragment):
        return [k for k in list(self.store) if fragment in k and self.get(k) is not None]

    def pipeline(self, transaction=True):
        return _Pipeline(self)


class _Pipeline:
    def __init__(self, redis):
        self.redis = redis
        self.calls = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return queue

    def execute(self):
        results = [getattr(self.redis, name)(*args, **kwargs) for name, args, kwargs in self.calls]
        self.calls = []
        return results
