"""
Login brute-force protection through the real /auth/login route.

Counters are keyed by the attacked account and by the client from
app.core.client_ip, so users sharing a proxy or NAT don't lock each other out,
and forged X-Forwarded-For headers can't buy an attacker fresh attempts.
"""

import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import brute_force
from app.auth.security import get_password_hash
from app.core import client_ip
from app.core.db import get_db
from app.main import app
from app.models.user import User
from fake_redis import FakeRedis

LOGIN = "/api/v1/auth/login"
NEXT_PROXY = "10.0.0.5"
WRONG = "definitely-wrong-password"


class Env:
    def __init__(self, db, redis):
        self.db, self.redis = db, redis
        self.passwords = {}

    def user(self, tag):
        email = f"{tag}@example.com"
        password = f"pw-{tag}-correct-horse"
        self.db.add(User(email=email, full_name=tag, hashed_password=get_password_hash(password), is_active=True))
        self.db.flush()
        self.passwords[email] = password
        return email

    def login(self, email, password=None, peer="198.51.100.20", headers=None):
        client = TestClient(app, client=(peer, 50000), raise_server_exceptions=False)
        return client.post(
            LOGIN,
            data={"username": email, "password": self.passwords.get(email) if password is None else password},
            headers=headers or {},
        )


@pytest.fixture
def env(db_session, monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(brute_force, "require_redis", lambda: redis)
    monkeypatch.setattr(client_ip.get_settings(), "TRUSTED_PROXY_IPS", NEXT_PROXY)
    # Pin the rate-limit clock inside one window, so slow (bcrypt) logins can't straddle a rollover
    window_start = time.time() // brute_force.LOGIN_RATE_WINDOW * brute_force.LOGIN_RATE_WINDOW
    monkeypatch.setattr(brute_force, "time", SimpleNamespace(time=lambda: window_start + 1))
    app.dependency_overrides[get_db] = lambda: db_session
    yield Env(db_session, redis)
    app.dependency_overrides.clear()


def test_five_failures_for_a_do_not_block_b_behind_same_proxy(env):
    a, b = env.user("proxy-a"), env.user("proxy-b")
    codes = [env.login(a, WRONG, peer=NEXT_PROXY).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401]
    assert env.login(b, peer=NEXT_PROXY).status_code == 200


def test_five_failures_for_a_do_not_block_b_on_same_nat(env):
    a, b = env.user("nat-a"), env.user("nat-b")
    for _ in range(5):
        env.login(a, WRONG, peer="198.51.100.77")
    assert env.login(b, peer="198.51.100.77").status_code == 200


def test_attacked_account_stays_locked_even_with_correct_password(env):
    a = env.user("locked-a")
    codes = [env.login(a, WRONG, headers={"X-Captcha-Token": ""}).status_code for _ in range(3)]
    assert codes == [401, 401, 401]
    # CAPTCHA from now on; failures with a solved CAPTCHA still count toward lockout
    with patch("app.auth.captcha_verify.verify_captcha_token", return_value=True):
        assert env.login(a, WRONG, headers={"X-Captcha-Token": "ok"}).status_code == 401
        assert env.login(a, WRONG, headers={"X-Captcha-Token": "ok"}).status_code == 429
        # Locked: the right password from anywhere is still refused
        assert env.login(a, headers={"X-Captcha-Token": "ok"}).status_code == 429
        assert env.login(a, peer="203.0.113.50", headers={"X-Captcha-Token": "ok"}).status_code == 429
        assert env.login(a, peer=NEXT_PROXY, headers={"X-Captcha-Token": "ok"}).status_code == 429


def test_forged_forwarded_for_rotation_does_not_reset_limits(env):
    a = env.user("rotate-a")
    codes = [env.login(a, WRONG, headers={"X-Forwarded-For": f"203.0.113.{i + 1}"}).status_code for i in range(12)]
    assert codes[:3] == [401, 401, 401]
    assert all(code in (400, 429) for code in codes[3:]), codes
    assert env.login(a, headers={"X-Forwarded-For": "203.0.113.250"}).status_code in (400, 429)
    # The forged values never became a counter identity
    forged = brute_force._h("203.0.113.1")
    assert not env.redis.keys_matching(forged)


def test_trusted_proxy_forwarded_clients_are_separate(env):
    a, b = env.user("fwd-a"), env.user("fwd-b")
    for _ in range(5):
        env.login(a, WRONG, peer=NEXT_PROXY, headers={"X-Forwarded-For": "203.0.113.10"})
    assert env.login(b, peer=NEXT_PROXY, headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 200
    # but client-level counters did follow the forwarded address
    assert env.redis.keys_matching(f"fail:client:{brute_force._h('203.0.113.10')}")


def test_password_spraying_from_one_client_hits_captcha_wall(env):
    victims = [env.user(f"spray-{i}") for i in range(11)]
    for email in victims[:10]:
        assert env.login(email, WRONG, peer="198.51.100.99").status_code == 401
    # 10 failures from one client: CAPTCHA for any further account from it
    assert env.login(victims[10], peer="198.51.100.99").status_code == 400
    # an unrelated client is unaffected
    assert env.login(victims[10], peer="198.51.100.100").status_code == 200


def test_spraying_through_shared_proxy_does_not_wall_other_users(env):
    victims = [env.user(f"shared-{i}") for i in range(12)]
    for email in victims[:11]:
        env.login(email, WRONG, peer=NEXT_PROXY)
    assert env.login(victims[11], peer=NEXT_PROXY).status_code == 200


def test_per_account_per_client_rate_limit(env):
    a = env.user("rate-a")
    codes = [env.login(a).status_code for _ in range(brute_force.LOGIN_RATE_LIMIT + 1)]
    assert codes[:-1] == [200] * brute_force.LOGIN_RATE_LIMIT
    assert codes[-1] == 429


def test_per_account_rate_limit_across_clients(env):
    a = env.user("rate-acct")
    codes = [
        env.login(a, peer=f"198.51.100.{i + 1}").status_code for i in range(brute_force.LOGIN_ACCOUNT_RATE_LIMIT + 1)
    ]
    assert codes[-1] == 429


def test_unknown_email_gets_the_same_responses(env):
    known = env.user("known")
    unknown = "nobody-here@example.com"
    r_known, r_unknown = env.login(known, WRONG), env.login(unknown, WRONG)

    def _body(resp):
        return {k: v for k, v in resp.json().items() if k != "request_id"}

    assert (r_known.status_code, _body(r_known)) == (r_unknown.status_code, _body(r_unknown))
    # Same progression to CAPTCHA for both, from different clients so only account counters apply
    for _ in range(2):
        env.login(known, WRONG, peer="198.51.100.31")
        env.login(unknown, WRONG, peer="198.51.100.32")
    assert env.login(known, WRONG, peer="198.51.100.31").status_code == 400
    assert env.login(unknown, WRONG, peer="198.51.100.32").status_code == 400


def test_success_resets_account_failures_but_not_client_failures(env):
    a = env.user("reset-a")
    for _ in range(2):
        env.login(a, WRONG)
    assert env.login(a).status_code == 200
    for _ in range(2):
        assert env.login(a, WRONG).status_code == 401
    client_fail = env.redis.get(f"{brute_force.LOGIN_PREFIX}fail:client:{brute_force._h('198.51.100.20')}")
    assert int(client_fail) == 4


def test_redis_failure_fails_closed(env, monkeypatch):
    a = env.user("redis-down")

    def _unavailable():
        # what app.core.cache.require_redis does when Redis is unreachable
        raise HTTPException(status_code=503, detail="Redis unavailable")

    monkeypatch.setattr(brute_force, "require_redis", _unavailable)
    assert env.login(a).status_code == 503


def test_redis_error_mid_request_does_not_allow_login(env):
    a = env.user("redis-flaky")
    env.redis.fail = True
    assert env.login(a).status_code >= 500


def test_login_sets_session_cookie_and_logout_revokes_it(env, monkeypatch):
    from app.auth import cookie_auth

    monkeypatch.setattr(cookie_auth, "require_redis", lambda: env.redis)
    a = env.user("cookie-a")
    client = TestClient(app, client=("198.51.100.20", 50000), raise_server_exceptions=False)
    resp = client.post(LOGIN, data={"username": a, "password": env.passwords[a]})
    assert resp.status_code == 200
    cookie = resp.cookies.get(client_ip.get_settings().AUTH_COOKIE_NAME)
    assert cookie and "httponly" in resp.headers["set-cookie"].lower()

    from app.auth.cookie_auth import is_token_blacklisted

    assert not is_token_blacklisted(cookie)
    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200
    assert is_token_blacklisted(cookie)
