"""
General API rate limiting: buckets come from identities a client can't mint.

A valid session gets its own bucket (so users behind one proxy don't share),
API keys get theirs under a per-client ceiling (so rotating made-up keys can't
escape), and anonymous traffic is keyed by the trusted client address.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import cookie_auth
from app.auth.security import create_access_token
from app.core import client_ip, rate_limit
from fake_redis import FakeRedis

LIMIT = 5
NEXT_PROXY = "10.0.0.5"


@pytest.fixture
def env(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(rate_limit, "require_redis", lambda: redis)
    monkeypatch.setattr(cookie_auth, "require_redis", lambda: redis)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", LIMIT)
    monkeypatch.setattr(client_ip.get_settings(), "TRUSTED_PROXY_IPS", NEXT_PROXY)

    test_app = FastAPI()
    test_app.add_middleware(rate_limit.RateLimitMiddleware)

    @test_app.get("/api/v1/thing")
    def _thing():
        return {"ok": True}

    def client(peer="198.51.100.20"):
        return TestClient(test_app, client=(peer, 50000))

    return redis, client


def _token(email, minutes=30):
    return create_access_token(data={"sub": email}, expires_delta=timedelta(minutes=minutes))


def _cookie(token):
    return {client_ip.get_settings().AUTH_COOKIE_NAME: token}


def _codes(client, n, **kwargs):
    return [client.get("/api/v1/thing", **kwargs).status_code for _ in range(n)]


def test_session_users_behind_one_proxy_have_separate_buckets(env):
    _, client = env
    proxy = client(NEXT_PROXY)
    proxy.cookies.update(_cookie(_token("u1@example.com")))
    assert _codes(proxy, LIMIT + 1)[-1] == 429

    other = client(NEXT_PROXY)
    other.cookies.update(_cookie(_token("u2@example.com")))
    assert other.get("/api/v1/thing").status_code == 200


def test_session_users_behind_one_nat_have_separate_buckets(env):
    _, client = env
    one, two = client("198.51.100.40"), client("198.51.100.40")
    one.cookies.update(_cookie(_token("nat1@example.com")))
    two.cookies.update(_cookie(_token("nat2@example.com")))
    assert _codes(one, LIMIT + 1)[-1] == 429
    assert two.get("/api/v1/thing").status_code == 200


def test_rotating_junk_api_keys_hits_the_client_ceiling(env):
    _, client = env
    c = client("198.51.100.50")
    codes = [
        c.get("/api/v1/thing", headers={"X-API-Key": f"hx_junk_{uuid4().hex}"}).status_code
        for _ in range(LIMIT * rate_limit.API_KEY_CLIENT_MULTIPLIER + 1)
    ]
    assert codes[:-1] == [200] * (LIMIT * rate_limit.API_KEY_CLIENT_MULTIPLIER)
    assert codes[-1] == 429


def test_session_with_rotating_junk_keys_stays_in_user_bucket(env):
    _, client = env
    c = client()
    c.cookies.update(_cookie(_token("rotator@example.com")))
    codes = [c.get("/api/v1/thing", headers={"X-API-Key": uuid4().hex}).status_code for _ in range(LIMIT + 1)]
    assert codes[-1] == 429


def test_api_key_rate_limit_still_applies_per_key(env):
    _, client = env
    key = f"hx_{uuid4().hex}"
    assert _codes(client("198.51.100.60"), LIMIT + 1, headers={"X-API-Key": key})[-1] == 429
    # a different key (another customer) on another address is unaffected
    assert client("198.51.100.61").get("/api/v1/thing", headers={"X-API-Key": f"hx_{uuid4().hex}"}).status_code == 200


def test_forged_forwarded_for_does_not_change_anonymous_bucket(env):
    _, client = env
    c = client("198.51.100.70")
    codes = [
        c.get("/api/v1/thing", headers={"X-Forwarded-For": f"203.0.113.{i + 1}"}).status_code for i in range(LIMIT + 1)
    ]
    assert codes[-1] == 429


def test_trusted_proxy_forwarded_anonymous_clients_are_separate(env):
    _, client = env
    proxy = client(NEXT_PROXY)
    assert _codes(proxy, LIMIT + 1, headers={"X-Forwarded-For": "203.0.113.20"})[-1] == 429
    assert proxy.get("/api/v1/thing", headers={"X-Forwarded-For": "203.0.113.21"}).status_code == 200


@pytest.mark.parametrize("kind", ["junk", "expired", "wrong-secret", "revoked"])
def test_unusable_sessions_fall_back_to_client_address(env, kind):
    redis, client = env
    c = client("198.51.100.80")

    def token():
        if kind == "junk":
            return uuid4().hex
        if kind == "expired":
            return _token(f"{uuid4().hex}@example.com", minutes=-5)
        if kind == "wrong-secret":
            import jwt

            return jwt.encode({"sub": f"{uuid4().hex}@example.com", "exp": 9999999999}, "not-the-secret", "HS256")
        tok = _token(f"{uuid4().hex}@example.com")
        cookie_auth.blacklist_token(tok)
        return tok

    codes = []
    for _ in range(LIMIT + 1):
        c.cookies.clear()
        c.cookies.update(_cookie(token()))
        codes.append(c.get("/api/v1/thing").status_code)
    assert codes[-1] == 429, codes


def test_redis_outage_fails_closed(env):
    redis, client = env
    redis.fail = True
    assert client().get("/api/v1/thing").status_code == 503
