"""
Auth0 sign-in: Authorization Code flow with PKCE, handled server-side.

The browser goes to Auth0's Universal Login; Auth0 redirects back to our
callback with a code, which we exchange (client secret + PKCE verifier) for an
ID token. After verifying the ID token we find or create the Heliox user and
set the usual httpOnly session cookie, so the rest of the app is unchanged.

Login state (state, nonce, PKCE verifier, post-login path) lives in Redis for
10 minutes and is deleted on first use, so a callback can't be replayed. It is
also tied to the browser that started the login through a short-lived cookie,
so a callback link started by someone else can't sign this browser in.

Accounts are found by Auth0 subject only. A matching email never links to an
existing account: see sign_in_user.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple, cast
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_password_hash
from app.core.cache import require_redis
from app.core.config import get_settings
from app.models.oauth_identity import OAuthIdentity, OAuthProvider
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = 600
_STATE_PREFIX = "auth0:state:"
TX_COOKIE_NAME = "heliox_auth0_tx"
TX_COOKIE_PATH = "/api/v1/auth/auth0"
_jwks_clients: Dict[str, jwt.PyJWKClient] = {}


class Auth0Error(Exception):
    """Sign-in can't complete; ``code`` is passed to /login as ?error=."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RedactCallbackQuery(logging.Filter):
    """Access logs include the query string, which on the callback holds the code and state."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            path, has_query, _ = str(args[2]).partition("?")
            if has_query and path.rstrip("/").endswith("/auth/auth0/callback"):
                record.args = (*args[:2], path, *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(RedactCallbackQuery())


def is_enabled() -> bool:
    s = get_settings()
    return bool(s.AUTH0_DOMAIN and s.AUTH0_CLIENT_ID and s.AUTH0_CLIENT_SECRET)


def require_legacy_auth() -> None:
    """Dependency for Heliox password/Google/SAML sign-in routes, which Auth0 replaces."""
    if not get_settings().LEGACY_AUTH_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password, Google and SAML sign-in are disabled. Sign in with Auth0.",
        )


def callback_url() -> str:
    s = get_settings()
    return s.AUTH0_CALLBACK_URL or f"{s.FRONTEND_URL.rstrip('/')}/api/v1/auth/auth0/callback"


def logout_url() -> str:
    s = get_settings()
    query = urlencode({"client_id": s.AUTH0_CLIENT_ID, "returnTo": f"{s.FRONTEND_URL.rstrip('/')}/login"})
    return f"https://{s.AUTH0_DOMAIN}/v2/logout?{query}"


def safe_redirect(path: Optional[str]) -> str:
    """Only same-site paths like /analytics; anything else (//host, https://, backslashes) is dropped."""
    if not path or not path.startswith("/") or path.startswith("//") or "\\" in path:
        return ""
    return path


# ── Starting sign-in ───────────────────────────────────────────────────────────


def tx_cookie_secure() -> bool:
    s = get_settings()
    return s.ENV in ("production", "staging") or callback_url().startswith("https://")


def _binding_hash(binding: str) -> str:
    return hashlib.sha256(binding.encode()).hexdigest()


def start_login(redirect: Optional[str], signup: bool = False) -> Tuple[str, str]:
    """Store state in Redis. Returns the Auth0 /authorize URL and the browser binding for the cookie."""
    s = get_settings()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    binding = secrets.token_urlsafe(32)

    require_redis().setex(
        _STATE_PREFIX + state,
        STATE_TTL_SECONDS,
        json.dumps(
            {
                "nonce": nonce,
                "code_verifier": code_verifier,
                "redirect": safe_redirect(redirect),
                "binding_sha256": _binding_hash(binding),
            }
        ),
    )

    params = {
        "response_type": "code",
        "client_id": s.AUTH0_CLIENT_ID,
        "redirect_uri": callback_url(),
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if signup:
        params["screen_hint"] = "signup"
    return f"https://{s.AUTH0_DOMAIN}/authorize?{urlencode(params)}", binding


def pop_state(state: str, binding: Optional[str]) -> Optional[dict]:
    """Delete the stored login state (single use). Returns it only for the browser that started the login."""
    raw = cast(Optional[str], require_redis().getdel(_STATE_PREFIX + state))
    if not raw or not binding:
        return None
    login_state = json.loads(raw)
    if not secrets.compare_digest(login_state.get("binding_sha256", ""), _binding_hash(binding)):
        return None
    return login_state


# ── Completing sign-in ─────────────────────────────────────────────────────────


def exchange_code(code: str, code_verifier: str) -> dict:
    s = get_settings()
    try:
        resp = httpx.post(
            f"https://{s.AUTH0_DOMAIN}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": s.AUTH0_CLIENT_ID,
                "client_secret": s.AUTH0_CLIENT_SECRET,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": callback_url(),
            },
            timeout=10,
        )
    except httpx.HTTPError as exc:
        raise Auth0Error("auth0_failed", f"token exchange failed: {exc}") from exc
    if resp.status_code != 200:
        raise Auth0Error("auth0_failed", f"token exchange failed: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise Auth0Error("auth0_failed", "token exchange returned invalid JSON") from exc


def _signing_key(token: str):
    domain = get_settings().AUTH0_DOMAIN
    client = _jwks_clients.get(domain)
    if client is None:
        client = jwt.PyJWKClient(f"https://{domain}/.well-known/jwks.json", cache_keys=True)
        _jwks_clients[domain] = client
    return client.get_signing_key_from_jwt(token).key


def verify_id_token(id_token: str, nonce: str) -> dict:
    """Check signature (Auth0 JWKS), issuer, audience, expiry and nonce."""
    s = get_settings()
    try:
        claims = jwt.decode(
            id_token,
            _signing_key(id_token),
            algorithms=["RS256"],
            audience=s.AUTH0_CLIENT_ID,
            issuer=f"https://{s.AUTH0_DOMAIN}/",
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise Auth0Error("auth0_failed", f"invalid ID token: {exc}") from exc
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise Auth0Error("auth0_failed", "ID token nonce mismatch")
    return claims


def _create_owned_team(db: Session, user: User) -> Team:
    """Same naming as /auth/register: "<name>'s Team", de-duplicated."""
    base = (user.full_name or user.email.split("@")[0] or "My").strip()
    team_name = f"{base}'s Team"
    if db.query(Team).filter(Team.name == team_name).first():
        team_name = f"{team_name} ({user.email.split('@')[0]})"
    team = Team(name=team_name)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    return team


def _create_account(db: Session, claims: dict, sub: str, email: str) -> Tuple[User, bool]:
    """A new user, their own team and the identity that links them to this Auth0 subject."""
    user = User(
        email=email,
        full_name=claims.get("name"),
        # Never used: Auth0 owns the password. Hashed so it can't match anything
        hashed_password=get_password_hash(secrets.token_urlsafe(32)),
        is_active=True,
        email_verified=True,
    )
    db.add(user)
    db.flush()
    team_id = _create_owned_team(db, user).id
    identity = OAuthIdentity(
        team_id=team_id,
        user_id=user.id,
        provider=OAuthProvider.AUTH0,
        provider_user_id=sub,
        email=email,
        email_verified=True,
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
    identity.last_login_at = datetime.now(timezone.utc)
    db.add(identity)
    db.commit()
    return user, True


def _find_or_create(db: Session, claims: dict, sub: str, email: str) -> Tuple[User, bool]:
    identity = (
        db.query(OAuthIdentity)
        .filter(OAuthIdentity.provider == OAuthProvider.AUTH0, OAuthIdentity.provider_user_id == sub)
        .first()
    )
    if identity is None:
        existing = db.query(User).filter(func.lower(User.email) == email).first()
        if existing is not None:
            raise Auth0Error("account_exists", f"no Auth0 link for existing account {existing.id}")
        return _create_account(db, claims, sub, email)

    user = db.get(User, identity.user_id)
    if user is None:
        raise Auth0Error("auth0_failed", f"identity for {sub} has no user")
    if not user.is_active:
        raise Auth0Error("account_disabled", f"user {user.id} is inactive")

    created_team = False
    if db.query(TeamMember).filter(TeamMember.user_id == user.id).first() is None:
        _create_owned_team(db, user)
        created_team = True
    identity.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user, created_team


def sign_in_user(db: Session, claims: dict) -> Tuple[User, bool]:
    """
    Find or create the Heliox user for verified Auth0 claims. Returns (user, created_team).

    Only a stored (provider, subject) identity signs in to an existing account.
    A matching email never links one, even a verified one: the account may have
    been registered by someone else ahead of time, and linking would hand its
    owner's password and sessions over the real owner's data. Such sign-ins are
    refused with ``account_exists``, changing nothing, until ownership is proven
    through a separate migration. Unverified emails can't create accounts either.
    """
    sub = claims["sub"]
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise Auth0Error("auth0_failed", "Auth0 did not return an email address")
    if claims.get("email_verified") is not True:
        raise Auth0Error("email_not_verified", f"email not verified for {sub}")

    # Two simultaneous first sign-ins: the unique indexes stop the loser, who then finds the winner's account
    for _ in range(2):
        try:
            return _find_or_create(db, claims, sub, email)
        except IntegrityError:
            db.rollback()
    raise Auth0Error("auth0_failed", f"could not create an account for {sub}")
