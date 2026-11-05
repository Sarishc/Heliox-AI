"""
Tests for Auth0 sign-in (Authorization Code + PKCE, server-side).

Auth0 is faked: a locally generated RSA key signs ID tokens, and the token
endpoint and JWKS lookup are replaced, so no network calls are made.
"""

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.api.routes.auth as auth_routes
import app.auth.auth0 as auth0
from app.core.config import get_settings
from app.core.db import get_db
from app.main import app
from app.models.oauth_identity import OAuthIdentity, OAuthProvider
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User

DOMAIN = "heliox-test.us.auth0.com"
CLIENT_ID = "test-client-id"
FRONTEND = "http://localhost:3000"

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def auth0_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "AUTH0_DOMAIN", DOMAIN)
    monkeypatch.setattr(settings, "AUTH0_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(settings, "AUTH0_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setattr(settings, "FRONTEND_URL", FRONTEND)
    monkeypatch.setattr(settings, "LEGACY_AUTH_ENABLED", False)
    # Verify signatures against our test key instead of fetching Auth0's JWKS
    monkeypatch.setattr(auth0, "_signing_key", lambda token: PRIVATE_KEY.public_key())
    return settings


@pytest.fixture
def client(db_session: Session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _id_token(nonce, *, sub="auth0|abc123", email="ada@example.com", verified=True, key=PRIVATE_KEY, **overrides):
    now = int(time.time())
    claims = {
        "iss": f"https://{DOMAIN}/",
        "aud": CLIENT_ID,
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "name": "Ada Lovelace",
        "nonce": nonce,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def _start_login(client, **params):
    resp = client.get("/api/v1/auth/auth0/login", params=params)
    assert resp.status_code == 302, resp.text
    query = parse_qs(urlparse(resp.headers["location"]).query)
    return resp, {k: v[0] for k, v in query.items()}


def _complete_login(client, monkeypatch, id_token_for, **start_params):
    """Run login -> fake Auth0 -> callback. id_token_for(nonce) builds the ID token."""
    _, auth_params = _start_login(client, **start_params)
    seen = {}

    def fake_token_exchange(code, code_verifier):
        seen["code"], seen["code_verifier"] = code, code_verifier
        return {"id_token": id_token_for(auth_params["nonce"]), "access_token": "unused"}

    monkeypatch.setattr(auth0, "exchange_code", fake_token_exchange)
    resp = client.get("/api/v1/auth/auth0/callback", params={"code": "auth-code", "state": auth_params["state"]})
    return resp, auth_params, seen


# ── Starting sign-in ───────────────────────────────────────────────────────────


def test_login_redirects_to_auth0_with_state_nonce_and_pkce(client):
    resp, params = _start_login(client, redirect="/analytics")

    location = urlparse(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"https://{DOMAIN}/authorize"
    assert params["client_id"] == CLIENT_ID
    assert params["response_type"] == "code"
    assert params["redirect_uri"] == f"{FRONTEND}/api/v1/auth/auth0/callback"
    assert set(params["scope"].split()) >= {"openid", "profile", "email"}
    assert params["code_challenge_method"] == "S256"
    assert params["state"] and params["nonce"] and params["code_challenge"]


def test_signup_opens_the_auth0_signup_screen(client):
    _, params = _start_login(client, signup="1")

    assert params["screen_hint"] == "signup"


def test_pkce_verifier_sent_to_token_endpoint_matches_challenge(client, monkeypatch):
    resp, auth_params, seen = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))

    digest = hashlib.sha256(seen["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == auth_params["code_challenge"]
    assert seen["code"] == "auth-code"


# ── Completing sign-in ─────────────────────────────────────────────────────────


def test_first_sign_in_creates_user_and_owned_team(client, db_session, monkeypatch):
    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))

    assert resp.status_code == 302
    assert resp.headers["location"] == f"{FRONTEND}/onboarding"
    assert get_settings().AUTH_COOKIE_NAME in resp.headers.get("set-cookie", "")

    user = db_session.query(User).filter(User.email == "ada@example.com").one()
    assert user.email_verified is True
    membership = db_session.query(TeamMember).filter(TeamMember.user_id == user.id).one()
    assert membership.role == TeamRole.OWNER
    identity = db_session.query(OAuthIdentity).filter(OAuthIdentity.user_id == user.id).one()
    assert identity.provider == OAuthProvider.AUTH0
    assert identity.provider_user_id == "auth0|abc123"


def test_returning_user_signs_in_without_a_new_team(client, db_session, monkeypatch):
    _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))
    teams_before = db_session.query(Team).count()

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce), redirect="/analytics")

    assert resp.headers["location"] == f"{FRONTEND}/analytics"
    assert db_session.query(Team).count() == teams_before
    assert db_session.query(User).filter(User.email == "ada@example.com").count() == 1


def test_existing_password_user_is_not_linked_by_email(client, db_session, monkeypatch):
    team = Team(name="Existing Team")
    user = User(email="ada@example.com", full_name="Ada", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.flush()
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.commit()

    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce), redirect="/")

    assert resp.headers["location"] == f"{FRONTEND}/login?error=account_exists"
    assert get_settings().AUTH_COOKIE_NAME not in resp.headers.get("set-cookie", "")
    assert db_session.query(OAuthIdentity).count() == 0
    assert db_session.query(Team).count() == 1


def test_unverified_email_is_refused(client, db_session, monkeypatch):
    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce, verified=False))

    assert resp.headers["location"] == f"{FRONTEND}/login?error=email_not_verified"
    assert get_settings().AUTH_COOKIE_NAME not in resp.headers.get("set-cookie", "")
    assert db_session.query(User).filter(User.email == "ada@example.com").count() == 0


@pytest.mark.parametrize(
    "bad_token",
    [
        lambda nonce: _id_token("someone-elses-nonce"),
        lambda nonce: _id_token(nonce, aud="another-app"),
        lambda nonce: _id_token(nonce, iss="https://evil.example.com/"),
        lambda nonce: _id_token(nonce, exp=int(time.time()) - 60),
        lambda nonce: _id_token(nonce, key=OTHER_KEY),
    ],
    ids=["nonce", "audience", "issuer", "expired", "signature"],
)
def test_invalid_id_tokens_are_rejected(client, db_session, monkeypatch, bad_token):
    resp, _, _ = _complete_login(client, monkeypatch, bad_token)

    assert resp.headers["location"] == f"{FRONTEND}/login?error=auth0_failed"
    assert get_settings().AUTH_COOKIE_NAME not in resp.headers.get("set-cookie", "")
    assert db_session.query(User).count() == 0


def test_state_cannot_be_replayed(client, monkeypatch):
    resp, auth_params, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce))
    assert resp.headers["location"].startswith(f"{FRONTEND}/onboarding")

    replay = client.get("/api/v1/auth/auth0/callback", params={"code": "auth-code", "state": auth_params["state"]})

    assert replay.headers["location"] == f"{FRONTEND}/login?error=auth0_state"


def test_auth0_error_is_sent_back_to_login(client):
    resp = client.get(
        "/api/v1/auth/auth0/callback", params={"error": "access_denied", "error_description": "User cancelled"}
    )

    assert resp.status_code == 302
    assert resp.headers["location"] == f"{FRONTEND}/login?error=auth0_denied"


@pytest.mark.parametrize("target", ["https://evil.example.com", "//evil.example.com", "/\\evil.example.com"])
def test_redirect_after_login_stays_on_heliox(client, monkeypatch, target):
    resp, _, _ = _complete_login(client, monkeypatch, lambda nonce: _id_token(nonce), redirect=target)

    assert resp.headers["location"] == f"{FRONTEND}/onboarding"


# ── Config and legacy sign-in ──────────────────────────────────────────────────


def test_auth_config_reports_auth0_and_logout_url(client):
    body = client.get("/api/v1/auth/config").json()

    assert body["auth0_enabled"] is True
    assert body["legacy_auth_enabled"] is False
    logout = urlparse(body["logout_url"])
    assert logout.netloc == DOMAIN and logout.path == "/v2/logout"
    assert parse_qs(logout.query) == {"client_id": [CLIENT_ID], "returnTo": [f"{FRONTEND}/login"]}


@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("post", "/api/v1/auth/login", {"data": {"username": "a@example.com", "password": "pw"}}),
        ("post", "/api/v1/auth/register", {"json": {"email": "a@example.com", "password": "Passw0rd!Passw0rd"}}),
        ("post", "/api/v1/auth/google/start", {"json": {"team_id": "00000000-0000-0000-0000-000000000000"}}),
    ],
)
def test_legacy_sign_in_is_disabled(client, method, path, kwargs):
    resp = getattr(client, method)(path, **kwargs)

    assert resp.status_code == 403
    assert "auth0" in resp.json()["message"].lower()


@pytest.mark.parametrize("path", ["/forgot-password", "/reset-password"])
def test_password_reset_routes_require_legacy_sign_in(path):
    """Checked on the route: a request here would put "password" in the /metrics path labels other tests assert on."""
    [route] = [r for r in auth_routes.router.routes if r.path == path]

    assert auth0.require_legacy_auth in [d.call for d in route.dependant.dependencies]
