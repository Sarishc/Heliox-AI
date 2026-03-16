"""Tests for onboarding wizard and status endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.db import get_db
from app.auth.deps import get_current_active_user
from app.models.team import Team
from app.models.user import User
from app.models.team_member import TeamMember, TeamRole
from app.models.team_api_key import TeamAPIKey
from app.integrations.models import IntegrationConnection
from app.integrations.base import IntegrationProvider, IntegrationStatus
from app.models.alert_settings import AlertSettings
from app.integrations.encryption import get_encryption


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
def user_no_team(db_session: Session) -> User:
    """User with no team membership."""
    user = User(
        email="newuser@example.com",
        full_name="New User",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_with_team(db_session: Session) -> tuple[User, Team]:
    """User with team, API key, no integration, no webhook."""
    team = Team(name="Acme Corp")
    user = User(
        email="owner@example.com",
        full_name="Owner",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)
    db_session.refresh(user)

    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.add(
        TeamAPIKey(
            team_id=team.id,
            key_name="Default key",
            key_hash=TeamAPIKey.hash_key("test-key"),
            is_active=True,
        )
    )
    db_session.commit()
    return user, team


@pytest.fixture
def user_with_full_setup(db_session: Session) -> tuple[User, Team]:
    """User with team, API key, integration, and Slack webhook."""
    team = Team(name="Full Team")
    user = User(
        email="full@example.com",
        full_name="Full User",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)
    db_session.refresh(user)

    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.add(
        TeamAPIKey(
            team_id=team.id,
            key_name="Key",
            key_hash=TeamAPIKey.hash_key("key"),
            is_active=True,
        )
    )
    enc = get_encryption()
    db_session.add(
        IntegrationConnection(
            team_id=team.id,
            provider=IntegrationProvider.AWS,
            name="AWS",
            config_encrypted=enc.encrypt_config({"role_arn": "arn:aws:iam::123:role/test"}),
            status=IntegrationStatus.ACTIVE,
        )
    )
    db_session.add(
        AlertSettings(
            team_id=team.id,
            enable_slack=True,
            slack_webhook_encrypted=enc.encrypt_string("https://hooks.slack.com/services/xxx"),
        )
    )
    db_session.commit()
    return user, team


@pytest.fixture
def viewer_user(db_session: Session) -> tuple[User, Team]:
    """Viewer role user - cannot manage integrations/webhook."""
    team = Team(name="Viewer Team")
    user = User(
        email="viewer@example.com",
        full_name="Viewer",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)
    db_session.refresh(user)
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.VIEWER))
    db_session.add(
        TeamAPIKey(
            team_id=team.id,
            key_name="Key",
            key_hash=TeamAPIKey.hash_key("k"),
            is_active=True,
        )
    )
    db_session.commit()
    return user, team


def test_onboarding_status_no_team(client: TestClient, user_no_team: User) -> None:
    """GET /onboarding/status returns has_team=false when user has no team."""
    def override_user():
        return user_no_team

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_team"] is False
        assert data["has_api_key"] is False
        assert data["has_integration"] is False
        assert data["has_slack_webhook"] is False
        assert data["can_manage"] is False
        assert data["role"] == "unknown"
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_onboarding_status_with_team(client: TestClient, user_with_team: tuple[User, Team]) -> None:
    """GET /onboarding/status returns correct checklist when user has team but no integration."""
    user, team = user_with_team

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_team"] is True
        assert data["has_api_key"] is True
        assert data["has_integration"] is False
        assert data["has_slack_webhook"] is False
        assert data["can_manage"] is True
        assert data["role"] == "owner"
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_onboarding_status_full_setup(client: TestClient, user_with_full_setup: tuple[User, Team]) -> None:
    """GET /onboarding/status returns all true when fully configured."""
    user, _ = user_with_full_setup

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_team"] is True
        assert data["has_api_key"] is True
        assert data["has_integration"] is True
        assert data["has_slack_webhook"] is True
        assert data["can_manage"] is True
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_onboarding_status_viewer_cannot_manage(client: TestClient, viewer_user: tuple[User, Team]) -> None:
    """Viewer role gets can_manage=false."""
    user, _ = viewer_user

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_team"] is True
        assert data["can_manage"] is False
        assert data["role"] == "viewer"
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_onboarding_status_requires_auth(client: TestClient) -> None:
    """GET /onboarding/status returns 401 when not authenticated."""
    resp = client.get("/api/v1/onboarding/status")
    assert resp.status_code == 401
