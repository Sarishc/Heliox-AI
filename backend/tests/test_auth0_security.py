"""
Security regressions for Auth0 sign-in: browser binding, account linking, invites and disabled accounts.

Auth0 is faked as in test_auth0_login, so no network calls are made.
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from test_auth0_login import (  # noqa: F401
    FRONTEND,
    _complete_login,
    _id_token,
    _start_login,
    auth0_settings,
    client,
)

import app.auth.auth0 as auth0
from app.auth.security import create_access_token, get_password_hash
from app.core.cache import require_redis
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app as fastapi_app
from app.models.base import Base
from app.models.oauth_identity import OAuthIdentity, OAuthProvider
from app.models.team import Team
from app.models.team_invite import TeamInvite, generate_invite_token, hash_invite_token
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User

CALLBACK = "/api/v1/auth/auth0/callback"
TX_COOKIE = "heliox_auth0_tx"
SESSION_COOKIE = get_settings().AUTH_COOKIE_NAME


def set_cookies(resp) -> list[str]:
    return resp.headers.get_list("set-cookie")


def session_was_issued(resp) -> bool:
    return any(c.startswith(f"{SESSION_COOKIE}=") and "max-age=0" not in c.lower() for c in set_cookies(resp))


def tx_cookie_was_cleared(resp) -> bool:
    return any(c.startswith(f"{TX_COOKIE}=") and "max-age=0" in c.lower() for c in set_cookies(resp))


def login_error(resp) -> str:
    return resp.headers["location"].removeprefix(f"{FRONTEND}/login?error=")


def forbid_token_exchange(monkeypatch):
    def fail(code, code_verifier):
        raise AssertionError("no code may be exchanged without a valid browser binding")

    monkeypatch.setattr(auth0, "exchange_code", fail)


@pytest.fixture
def other_browser():
    return TestClient(fastapi_app, follow_redirects=False)


# ── Login CSRF ───────────────────────────────────────────────────────────────


def test_login_sets_a_short_lived_httponly_lax_cookie_unrelated_to_state(client):
    resp, params = _start_login(client)

    [cookie] = [c for c in set_cookies(resp) if c.startswith(f"{TX_COOKIE}=")]
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "max-age=600" in lowered
    assert "path=/api/v1/auth/auth0" in lowered
    assert "domain=" not in lowered
    assert "secure" not in lowered  # plain http in development
    value = cookie.split(";")[0].split("=", 1)[1]
    assert value not in (params["state"], params["nonce"], params["code_challenge"])


@pytest.mark.parametrize(
    "env,callback,secure",
    [
        ("production", "", True),
        ("staging", "", True),
        ("dev", "https://app.example.com/api/v1/auth/auth0/callback", True),
        ("dev", "http://localhost:3000/api/v1/auth/auth0/callback", False),
    ],
)
def test_login_cookie_is_secure_over_https(monkeypatch, env, callback, secure):
    settings = get_settings()
    monkeypatch.setattr(settings, "ENV", env)
    monkeypatch.setattr(settings, "AUTH0_CALLBACK_URL", callback)
    assert auth0.tx_cookie_secure() is secure


def test_login_and_callback_cookies_carry_secure_over_https(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "AUTH0_CALLBACK_URL", "https://app.example.com/api/v1/auth/auth0/callback")
    resp, _ = _start_login(client)
    assert all("secure" in c.lower() for c in set_cookies(resp) if c.startswith(f"{TX_COOKIE}="))

    done = client.get(CALLBACK, params={"error": "access_denied"})
    assert all("secure" in c.lower() for c in set_cookies(done) if c.startswith(f"{TX_COOKIE}="))


def test_redis_holds_only_a_hash_of_the_browser_binding(client):
    resp, params = _start_login(client)
    binding = client.cookies[TX_COOKIE]
    raw = require_redis().get(auth0._STATE_PREFIX + params["state"])
    assert binding not in raw
    assert json.loads(raw)["binding_sha256"]


def test_callback_from_browser_a_cannot_authenticate_browser_b(client, other_browser, db_session, monkeypatch):
    """The attack: start login as yourself, then send your callback link to a victim."""
    _, params = _start_login(client)
    forbid_token_exchange(monkeypatch)

    resp = other_browser.get(CALLBACK, params={"code": "attacker-code", "state": params["state"]})

    assert login_error(resp) == "auth0_state"
    assert not session_was_issued(resp)
    assert db_session.query(User).count() == 0


def test_browser_b_with_its_own_login_in_progress_is_still_refused(client, other_browser, db_session, monkeypatch):
    _, params = _start_login(client)
    _start_login(other_browser)
    forbid_token_exchange(monkeypatch)

    resp = other_browser.get(CALLBACK, params={"code": "attacker-code", "state": params["state"]})

    assert login_error(resp) == "auth0_state"
    assert not session_was_issued(resp)
    assert tx_cookie_was_cleared(resp)


def test_a_state_tried_from_the_wrong_browser_is_spent(client, other_browser, monkeypatch):
    _, params = _start_login(client)
    forbid_token_exchange(monkeypatch)
    other_browser.get(CALLBACK, params={"code": "c", "state": params["state"]})

    resp = client.get(CALLBACK, params={"code": "c", "state": params["state"]})

    assert login_error(resp) == "auth0_state"
    assert not session_was_issued(resp)


def test_missing_binding_cookie_is_refused(client, monkeypatch):
    _, params = _start_login(client)
    client.cookies.delete(TX_COOKIE)
    forbid_token_exchange(monkeypatch)

    resp = client.get(CALLBACK, params={"code": "c", "state": params["state"]})

    assert login_error(resp) == "auth0_state"
    assert not session_was_issued(resp)


def test_tampered_binding_cookie_is_refused(client, monkeypatch):
    _, params = _start_login(client)
    client.cookies.set(TX_COOKIE, "not-the-binding", path="/api/v1/auth/auth0")
    forbid_token_exchange(monkeypatch)

    resp = client.get(CALLBACK, params={"code": "c", "state": params["state"]})

    assert login_error(resp) == "auth0_state"


def test_expired_state_is_refused(client, monkeypatch):
    _, params = _start_login(client)
    require_redis().delete(auth0._STATE_PREFIX + params["state"])
    forbid_token_exchange(monkeypatch)

    resp = client.get(CALLBACK, params={"code": "c", "state": params["state"]})

    assert login_error(resp) == "auth0_state"
    assert tx_cookie_was_cleared(resp)


@pytest.mark.parametrize("query", [{"code": "c"}, {"state": "s"}, {"code": "c", "state": "unknown"}, {}])
def test_incomplete_or_unknown_callbacks_are_refused(client, monkeypatch, query):
    _start_login(client)
    forbid_token_exchange(monkeypatch)

    resp = client.get(CALLBACK, params=query)

    assert login_error(resp) == "auth0_state"
    assert tx_cookie_was_cleared(resp)


def test_replay_in_the_same_browser_is_refused_and_issues_nothing(client, monkeypatch):
    first, params, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))
    assert session_was_issued(first)

    replay = client.get(CALLBACK, params={"code": "auth-code", "state": params["state"]})

    assert login_error(replay) == "auth0_state"
    assert not session_was_issued(replay)


def test_binding_cookie_is_cleared_on_success(client, monkeypatch):
    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))
    assert session_was_issued(resp)
    assert tx_cookie_was_cleared(resp)
    assert TX_COOKIE not in client.cookies


def test_binding_cookie_is_cleared_when_sign_in_fails(client, monkeypatch):
    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token("wrong-nonce"))
    assert login_error(resp) == "auth0_failed"
    assert tx_cookie_was_cleared(resp)


def test_binding_cookie_is_cleared_and_state_spent_when_auth0_reports_an_error(client):
    _, params = _start_login(client)

    resp = client.get(CALLBACK, params={"error": "access_denied", "state": params["state"]})

    assert login_error(resp) == "auth0_denied"
    assert tx_cookie_was_cleared(resp)
    assert require_redis().get(auth0._STATE_PREFIX + params["state"]) is None


def test_state_code_and_tokens_stay_out_of_the_logs(client, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    tokens = {}

    def id_token_for(nonce):
        tokens["id"] = _id_token(nonce)
        return tokens["id"]

    resp, params, _ = _complete_login(client, monkeypatch, id_token_for)
    client.get(
        CALLBACK,
        params={"error": "access_denied", "error_description": "secret-description", "state": "state-in-error"},
    )

    # httpx logs here belong to the test client, not the application
    logged = "\n".join(r.getMessage() for r in caplog.records if r.name != "httpx")
    for secret in (params["state"], params["nonce"], "auth-code", tokens["id"], "secret-description", "state-in-error"):
        assert secret not in logged


@pytest.mark.parametrize("path", [CALLBACK, f"{CALLBACK}/"], ids=["callback", "trailing_slash"])
def test_access_log_keeps_the_callback_path_but_not_its_query(path):
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", f"{path}?code=secret-code&state=secret-state", "1.1", 302),
        None,
    )
    assert auth0.RedactCallbackQuery().filter(record) is True
    message = record.getMessage()
    assert path in message
    assert "secret-code" not in message and "secret-state" not in message


def test_access_log_leaves_other_requests_alone():
    args = ("127.0.0.1:1", "GET", "/api/v1/me?x=1", "1.1", 200)
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', args, None)
    auth0.RedactCallbackQuery().filter(record)
    assert record.args == args


def test_an_unusable_token_response_fails_safely(client, monkeypatch):
    class NotJson:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(auth0.httpx, "post", lambda *a, **k: NotJson())
    _, params = _start_login(client)

    resp = client.get(CALLBACK, params={"code": "c", "state": params["state"]})

    assert login_error(resp) == "auth0_failed"
    assert tx_cookie_was_cleared(resp)


# ── Account pre-hijacking ────────────────────────────────────────────────────


def _password_account(db_session, email, *, verified):
    team = Team(name=f"Team {uuid4().hex[:8]}")
    user = User(
        email=email,
        full_name="Existing",
        hashed_password=get_password_hash("attacker-knows-this"),
        is_active=True,
        email_verified=verified,
    )
    db_session.add_all([team, user])
    db_session.flush()
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.commit()
    return user, team


def test_prehijack_sequence_gives_the_attacker_nothing(client, other_browser, db_session, monkeypatch):
    """Attacker registers the victim's email and keeps a session; the victim then signs in through Auth0."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LEGACY_AUTH_ENABLED", True)
    registered = other_browser.post(
        "/api/v1/auth/register", json={"email": "victim@example.com", "password": "Attacker!Passw0rd#1"}
    )
    assert registered.status_code == 201, registered.text
    login = other_browser.post(
        "/api/v1/auth/login", data={"username": "victim@example.com", "password": "Attacker!Passw0rd#1"}
    )
    assert login.status_code == 200, login.text
    attacker_user = db_session.query(User).filter(User.email == "victim@example.com").one()
    password_before = attacker_user.hashed_password
    teams_before = db_session.query(Team).count()

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, email="victim@example.com"))

    assert login_error(resp) == "account_exists"
    assert not session_was_issued(resp)
    assert SESSION_COOKIE not in client.cookies
    db_session.expire_all()
    assert attacker_user.email_verified is False  # never upgraded by Auth0's claim
    assert attacker_user.hashed_password == password_before
    assert db_session.query(OAuthIdentity).count() == 0
    assert db_session.query(Team).count() == teams_before
    # The attacker's account stays exactly what it was: it holds nothing of the victim's
    me = other_browser.get("/api/v1/me")
    assert me.json()["team_id"] == str(
        db_session.query(TeamMember).filter(TeamMember.user_id == attacker_user.id).one().team_id
    )


@pytest.mark.parametrize("verified", [True, False], ids=["verified_account", "unverified_account"])
@pytest.mark.parametrize("email", ["ada@example.com", "ADA@Example.com"], ids=["same_case", "other_case"])
def test_matching_email_never_links_an_existing_account(client, db_session, monkeypatch, verified, email):
    user, team = _password_account(db_session, "ada@example.com", verified=verified)

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, email=email))

    assert login_error(resp) == "account_exists"
    assert not session_was_issued(resp)
    assert db_session.query(OAuthIdentity).count() == 0
    # Nothing was deleted, merged or changed
    db_session.expire_all()
    assert db_session.get(User, user.id).email_verified is verified
    membership = db_session.query(TeamMember).filter(TeamMember.user_id == user.id).one()
    assert (membership.team_id, membership.role) == (team.id, TeamRole.OWNER)
    assert db_session.query(User).count() == 1


def test_explicitly_linked_subject_signs_in_to_its_account(client, db_session, monkeypatch):
    user, team = _password_account(db_session, "ada@example.com", verified=True)
    db_session.add(
        OAuthIdentity(
            team_id=team.id,
            user_id=user.id,
            provider=OAuthProvider.AUTH0,
            provider_user_id="auth0|abc123",
            email="ada@example.com",
            email_verified=True,
        )
    )
    db_session.commit()
    password_before = user.hashed_password

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce), redirect="/analytics")

    assert resp.headers["location"] == f"{FRONTEND}/analytics"
    assert session_was_issued(resp)
    db_session.expire_all()
    assert db_session.get(User, user.id).hashed_password == password_before


def test_subject_is_trusted_over_a_changed_email(client, db_session, monkeypatch):
    """A linked subject whose Auth0 email now matches someone else stays on its own account."""
    _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, email="ada@example.com"))
    ada = db_session.query(User).filter(User.email == "ada@example.com").one()
    other, _ = _password_account(db_session, "grace@example.com", verified=True)

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, email="grace@example.com"))

    assert session_was_issued(resp)
    db_session.expire_all()
    assert db_session.get(User, ada.id).email == "ada@example.com"
    assert db_session.query(OAuthIdentity).filter(OAuthIdentity.user_id == other.id).count() == 0
    me = client.get("/api/v1/me")
    assert me.json()["team_id"] == str(db_session.query(TeamMember).filter(TeamMember.user_id == ada.id).one().team_id)


def test_a_disabled_linked_account_cannot_sign_in(client, db_session, monkeypatch):
    _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))
    db_session.query(User).filter(User.email == "ada@example.com").update({"is_active": False})
    db_session.commit()

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))

    assert login_error(resp) == "account_disabled"
    assert not session_was_issued(resp)


def test_losing_a_first_login_race_signs_in_to_the_winners_account(db_session, monkeypatch):
    """The unique index stops the loser; it then finds the winner's identity instead of failing or duplicating."""
    claims = {"sub": "auth0|race", "email": "race@example.com", "email_verified": True, "name": "Race"}
    real_create = auth0._create_account
    calls = []

    def lose_the_race(db, *args):
        calls.append(1)
        if len(calls) == 1:
            real_create(db, *args)
            db.commit()  # the other request got there first
            raise IntegrityError("insert", {}, Exception("uq_oauth_provider_user"))
        raise AssertionError("the retry must find the identity, not create again")

    monkeypatch.setattr(auth0, "_create_account", lose_the_race)

    user, created_team = auth0.sign_in_user(db_session, claims)

    assert user.email == "race@example.com"
    assert created_team is False
    assert db_session.query(User).count() == 1
    assert db_session.query(OAuthIdentity).count() == 1


def test_a_collision_that_keeps_failing_ends_in_a_safe_error(db_session, monkeypatch):
    claims = {"sub": "auth0|race", "email": "race@example.com", "email_verified": True}

    def always_collide(db, *args):
        raise IntegrityError("insert", {}, Exception("uq"))

    monkeypatch.setattr(auth0, "_create_account", always_collide)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.sign_in_user(db_session, claims)
    assert exc.value.code == "auth0_failed"


@pytest.mark.skipif(
    not os.environ.get("HELIOX_MIGRATION_TEST_SERVER_URL"),
    reason="needs a disposable PostgreSQL server (HELIOX_MIGRATION_TEST_SERVER_URL)",
)
def test_simultaneous_first_logins_on_postgres_create_one_account():
    server = make_url(os.environ["HELIOX_MIGRATION_TEST_SERVER_URL"])
    name = f"auth0_race_{uuid4().hex[:12]}"
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(server.set(database=name))
    try:
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        claims = {"sub": "auth0|pg-race", "email": "pg-race@example.com", "email_verified": True, "name": "Race"}
        real_create = auth0._create_account
        both_ready = threading.Barrier(2, timeout=20)
        results, failures = [], []

        def racing_create(db, *args):
            both_ready.wait()  # both requests have seen no identity and no user
            return real_create(db, *args)

        def sign_in():
            with sessions() as db:
                try:
                    user, created = auth0.sign_in_user(db, claims)
                    results.append((user.id, created))
                except Exception as exc:  # noqa: BLE001
                    failures.append(exc)

        original = auth0._create_account
        auth0._create_account = racing_create
        try:
            threads = [threading.Thread(target=sign_in) for _ in range(2)]
            [t.start() for t in threads]
            [t.join(30) for t in threads]
        finally:
            auth0._create_account = original

        assert failures == []
        assert len({user_id for user_id, _ in results}) == 1
        assert sorted(created for _, created in results) == [False, True]
        with sessions() as db:
            assert db.query(User).count() == 1
            assert db.query(Team).count() == 1
            assert db.query(TeamMember).count() == 1
            assert db.query(OAuthIdentity).count() == 1
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


# ── Invites without legacy sign-in ───────────────────────────────────────────


def _invite(db_session, email, role=TeamRole.MEMBER):
    team = Team(name=f"Team {uuid4().hex[:8]}")
    db_session.add(team)
    db_session.flush()
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email=email,
        role=role.value,
        token_hash=hash_invite_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(invite)
    db_session.commit()
    return token, invite, team


def _accept(browser, token, **body):
    return browser.post(f"/api/v1/invite/{token}/accept", json=body)


def test_invite_cannot_create_a_password_login_when_legacy_is_off(client, db_session):
    token, invite, _ = _invite(db_session, "new@example.com")

    resp = _accept(client, token, email="new@example.com", password="Passw0rd!Passw0rd", full_name="New")

    assert resp.status_code == 403
    assert not session_was_issued(resp)
    assert db_session.query(User).filter(User.email == "new@example.com").count() == 0
    db_session.expire_all()
    assert db_session.get(TeamInvite, invite.id).accepted_at is None  # still usable after signing in


def test_invite_still_works_for_a_signed_in_auth0_user(client, db_session, monkeypatch):
    token, invite, team = _invite(db_session, "ada@example.com")
    _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, email="ada@example.com"))

    resp = _accept(client, token, email="ada@example.com")

    assert resp.status_code == 200, resp.text
    user = db_session.query(User).filter(User.email == "ada@example.com").one()
    assert db_session.query(TeamMember).filter_by(team_id=team.id, user_id=user.id).one().role == TeamRole.MEMBER


def test_invite_still_refuses_another_signed_in_auth0_user(client, db_session, monkeypatch):
    token, _, team = _invite(db_session, "someone-else@example.com")
    _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, email="ada@example.com"))

    resp = _accept(client, token, email="someone-else@example.com")

    assert resp.status_code == 400
    assert db_session.query(TeamMember).filter_by(team_id=team.id).count() == 0


def test_invite_token_is_still_verified_when_legacy_is_off(client):
    resp = _accept(client, "not-a-real-token", email="new@example.com", password="Passw0rd!Passw0rd")
    assert resp.status_code == 404


def test_invite_can_still_create_a_password_login_when_legacy_is_on(client, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "LEGACY_AUTH_ENABLED", True)
    token, _, _ = _invite(db_session, "new@example.com")

    resp = _accept(client, token, email="new@example.com", password="Passw0rd!Passw0rd")

    assert resp.status_code == 200, resp.text
    assert session_was_issued(resp)


# ── Disabled accounts ────────────────────────────────────────────────────────


@pytest.fixture
def signed_in(db_session):
    def _get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = _get_db
    team = Team(name=f"Team {uuid4().hex[:8]}")
    user = User(email="member@example.com", full_name="M", hashed_password="x", is_active=True, email_verified=True)
    db_session.add_all([team, user])
    db_session.flush()
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.commit()
    browser = TestClient(fastapi_app, follow_redirects=False, base_url="https://testserver")
    browser.cookies.set(SESSION_COOKIE, create_access_token(data={"sub": user.email}))
    try:
        yield browser, user, team
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


PROTECTED = {
    "get_current_user": "/api/v1/onboarding/status",
    "verify_team_api_key_or_session": "/api/v1/anomalies",
    "get_team_api_key_or_session_optional": "/api/v1/forecast/spend?horizon_days=7&allow_empty=true",
    "require_team_admin_or_api_key": "/api/v1/budgets",
    "events_team_resolution": "/api/v1/events/recent",
}


@pytest.mark.parametrize("dependency,path", PROTECTED.items(), ids=PROTECTED.keys())
def test_disabling_an_account_ends_its_live_session(signed_in, db_session, monkeypatch, dependency, path):
    browser, user, _ = signed_in
    monkeypatch.setattr(get_settings(), "ENV", "production")  # the optional dependency only enforces there
    assert browser.get(path).status_code != 401

    user.is_active = False
    db_session.commit()

    assert browser.get(path).status_code == 401


def test_me_reports_no_team_for_a_disabled_account(signed_in, db_session):
    browser, user, team = signed_in
    assert browser.get("/api/v1/me").json()["team_id"] == str(team.id)

    user.is_active = False
    db_session.commit()

    assert browser.get("/api/v1/me").json()["team_id"] == ""


def test_reenabling_an_account_restores_only_its_own_team(signed_in, db_session):
    browser, user, team = signed_in
    other = Team(name=f"Team {uuid4().hex[:8]}")
    db_session.add(other)
    user.is_active = False
    db_session.commit()
    assert browser.get("/api/v1/onboarding/status").status_code == 401

    user.is_active = True
    db_session.commit()

    assert browser.get("/api/v1/onboarding/status").status_code == 200
    assert browser.get("/api/v1/me").json()["team_id"] == str(team.id)
