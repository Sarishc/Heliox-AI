"""
OAuth session flow integration tests.

Verifies:
- OAuth callback sets httpOnly cookie
- Redirect URL contains no token
- Session cookie allows access to protected route
"""

import pytest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.db import get_db
from app.models.team import Team
from app.models.user import User
from app.models.team_member import TeamMember, TeamRole
from app.auth.oauth_google import build_google_auth_url
from app.auth.security import get_password_hash


def override_get_db(db_session: Session):
    def _get_db():
        try:
            yield db_session
        finally:
            pass

    return _get_db


@pytest.fixture
def client(db_session: Session) -> TestClient:
    app.dependency_overrides[get_db] = override_get_db(db_session)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def team_with_sso(db_session: Session) -> Team:
    """Create team with SSO enabled."""
    team = Team(
        name="SSO Team",
        sso_enabled=True,
        sso_enforce_domain=False,
    )
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


@pytest.fixture
def oauth_state(team_with_sso: Team) -> tuple[str, str]:
    """Create valid OAuth state for callback."""
    from app.core.config import get_settings

    settings = get_settings()
    auth_url, state = build_google_auth_url(
        team_id=str(team_with_sso.id),
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
        frontend_redirect="http://localhost:3000",
    )
    return state, str(team_with_sso.id)


@patch("app.api.routes.auth_oauth.get_google_userinfo", new_callable=AsyncMock)
@patch("app.api.routes.auth_oauth.exchange_code_for_token", new_callable=AsyncMock)
def test_oauth_callback_sets_cookie_and_redirects_without_token(
    mock_exchange: AsyncMock,
    mock_userinfo: AsyncMock,
    client: TestClient,
    team_with_sso: Team,
    oauth_state: tuple[str, str],
    db_session: Session,
) -> None:
    """OAuth callback sets httpOnly cookie and redirects to dashboard with no token in URL."""
    state, team_id = oauth_state

    # Create user for OAuth
    user = User(
        email="oauth@example.com",
        full_name="OAuth User",
        hashed_password=get_password_hash("unused"),
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(TeamMember(user_id=user.id, team_id=team_with_sso.id, role=TeamRole.MEMBER))
    db_session.commit()

    mock_exchange.return_value = {"access_token": "google-token", "expires_in": 3600}
    mock_userinfo.return_value = {
        "id": "google-123",
        "email": "oauth@example.com",
        "name": "OAuth User",
        "verified_email": True,
    }

    resp = client.get(
        f"/api/v1/auth/google/callback?code=test-code&state={state}",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "location" in resp.headers
    redirect_url = resp.headers["location"]
    assert "token=" not in redirect_url
    assert "team_id=" not in redirect_url
    assert redirect_url.rstrip("/").endswith("localhost:3000") or "localhost:3000" in redirect_url

    # Verify Set-Cookie header
    set_cookie = resp.headers.get("set-cookie", "")
    assert "heliox_session=" in set_cookie or "session=" in set_cookie.lower()
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()
    assert "SameSite=Strict" in set_cookie or "samesite=strict" in set_cookie.lower()


@patch("app.api.routes.auth_oauth.get_google_userinfo", new_callable=AsyncMock)
@patch("app.api.routes.auth_oauth.exchange_code_for_token", new_callable=AsyncMock)
def test_oauth_session_allows_protected_route_access(
    mock_exchange: AsyncMock,
    mock_userinfo: AsyncMock,
    client: TestClient,
    team_with_sso: Team,
    oauth_state: tuple[str, str],
) -> None:
    """After OAuth login, session cookie allows access to /api/v1/me."""
    state, _ = oauth_state

    mock_exchange.return_value = {"access_token": "google-token", "expires_in": 3600}
    mock_userinfo.return_value = {
        "id": "google-456",
        "email": "sso_new@example.com",
        "name": "SSO New User",
        "verified_email": True,
    }

    # OAuth callback creates user and sets cookie
    resp = client.get(
        f"/api/v1/auth/google/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 302

    # TestClient preserves cookies; access protected route
    me_resp = client.get("/api/v1/me")
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data.get("team_id") == str(team_with_sso.id)
    assert "role" in data
