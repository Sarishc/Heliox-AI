"""Tests for team invitation flow."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.main import app
from app.models.team import Team
from app.models.team_invite import TeamInvite, generate_invite_token, hash_invite_token
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User


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
def owner_user(db_session: Session) -> tuple[User, Team]:
    """Owner of a team."""
    team = Team(name="Acme")
    user = User(
        email="owner@test.com",
        full_name="Owner",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)
    db_session.refresh(user)
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.commit()
    return user, team


@pytest.fixture
def admin_user(db_session: Session) -> tuple[User, Team]:
    """Admin of a team."""
    team = Team(name="Beta")
    user = User(
        email="admin@test.com",
        full_name="Admin",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)
    db_session.refresh(user)
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.ADMIN))
    db_session.commit()
    return user, team


@pytest.fixture
def viewer_user(db_session: Session) -> tuple[User, Team]:
    """Viewer - cannot create invites."""
    team = Team(name="Gamma")
    user = User(
        email="viewer@test.com",
        full_name="Viewer",
        hashed_password="hashed",
        is_active=True,
    )
    db_session.add_all([team, user])
    db_session.commit()
    db_session.refresh(team)
    db_session.refresh(user)
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.VIEWER))
    db_session.commit()
    return user, team


def test_owner_can_create_invite(client: TestClient, owner_user: tuple[User, Team]) -> None:
    """Owner can create an invite."""
    user, team = owner_user

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.post(
            f"/api/v1/teams/{team.id}/invites",
            json={"email": "new@test.com", "role": "viewer"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@test.com"
        assert data["role"] == "viewer"
        assert "invite_link" in data
        assert str(team.id) in data["invite_link"] or team.id.hex in data["invite_link"]
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_admin_can_create_invite(client: TestClient, admin_user: tuple[User, Team]) -> None:
    """Admin can create an invite."""
    user, team = admin_user

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.post(
            f"/api/v1/teams/{team.id}/invites",
            json={"email": "new@test.com", "role": "admin"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "admin"
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_viewer_cannot_create_invite(client: TestClient, viewer_user: tuple[User, Team]) -> None:
    """Viewer cannot create invites."""
    user, team = viewer_user

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.post(
            f"/api/v1/teams/{team.id}/invites",
            json={"email": "new@test.com", "role": "viewer"},
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_validate_invite_token(client: TestClient, owner_user: tuple[User, Team], db_session: Session) -> None:
    """GET /invite/{token} returns invite info for valid token."""
    _, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email="invited@test.com",
        role="viewer",
        token_hash=hash_invite_token(token),
        invited_by_user_id=owner_user[0].id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invite)
    db_session.commit()

    resp = client.get(f"/api/v1/invite/{token}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["team_name"] == "Acme"
    assert data["email"] == "invited@test.com"
    assert data["role"] == "viewer"


def test_validate_expired_invite(client: TestClient, owner_user: tuple[User, Team], db_session: Session) -> None:
    """Expired invite returns 404."""
    _, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email="invited@test.com",
        role="viewer",
        token_hash=hash_invite_token(token),
        invited_by_user_id=owner_user[0].id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(invite)
    db_session.commit()

    resp = client.get(f"/api/v1/invite/{token}")
    assert resp.status_code == 404


def test_accept_invite_new_user(client: TestClient, owner_user: tuple[User, Team], db_session: Session) -> None:
    """New user can accept invite with password (creates account + membership)."""
    _, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email="brandnew@test.com",
        role="viewer",
        token_hash=hash_invite_token(token),
        invited_by_user_id=owner_user[0].id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invite)
    db_session.commit()

    resp = client.post(
        f"/api/v1/invite/{token}/accept",
        json={
            "email": "brandnew@test.com",
            "password": "securepass123",
            "full_name": "Brand New",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "team_id" in data

    # Verify membership created
    from app.crud import user as crud_user
    from app.crud import team_member as crud_team_member

    user = crud_user.get_by_email(db_session, email="brandnew@test.com")
    assert user is not None
    membership = crud_team_member.get_by_team_and_user(db_session, team_id=team.id, user_id=user.id)
    assert membership is not None
    assert membership.role == TeamRole.VIEWER


def test_accept_invite_wrong_email_rejected(
    client: TestClient, owner_user: tuple[User, Team], db_session: Session
) -> None:
    """Accept with wrong email is rejected."""
    _, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email="correct@test.com",
        role="viewer",
        token_hash=hash_invite_token(token),
        invited_by_user_id=owner_user[0].id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invite)
    db_session.commit()

    resp = client.post(
        f"/api/v1/invite/{token}/accept",
        json={"email": "wrong@test.com", "password": "pass123"},
    )
    assert resp.status_code == 400


def test_accept_invite_duplicate_membership_handled(
    client: TestClient, owner_user: tuple[User, Team], db_session: Session
) -> None:
    """Accept when already a member returns success (idempotent)."""
    user, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email=user.email,
        role="viewer",
        token_hash=hash_invite_token(token),
        invited_by_user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invite)
    db_session.commit()

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.post(
            f"/api/v1/invite/{token}/accept",
            json={"email": user.email},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "already a member" in data.get("message", "")
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_list_invites_owner(client: TestClient, owner_user: tuple[User, Team], db_session: Session) -> None:
    """Owner can list pending invites."""
    user, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email="pending@test.com",
        role="admin",
        token_hash=hash_invite_token(token),
        invited_by_user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invite)
    db_session.commit()

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.get(f"/api/v1/teams/{team.id}/invites")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        emails = [i["email"] for i in data]
        assert "pending@test.com" in emails
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_revoke_invite(client: TestClient, owner_user: tuple[User, Team], db_session: Session) -> None:
    """Owner can revoke a pending invite."""
    user, team = owner_user
    token = generate_invite_token()
    invite = TeamInvite(
        team_id=team.id,
        email="torevoke@test.com",
        role="viewer",
        token_hash=hash_invite_token(token),
        invited_by_user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(invite)
    db_session.commit()
    invite_id = invite.id

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.delete(f"/api/v1/teams/{team.id}/invites/{invite_id}")
        assert resp.status_code == 204

        # Token should no longer validate
        resp2 = client.get(f"/api/v1/invite/{token}")
        assert resp2.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


def test_invite_response_excludes_token(client: TestClient, owner_user: tuple[User, Team]) -> None:
    """List/create response must not expose raw token."""
    user, team = owner_user

    def override_user():
        return user

    app.dependency_overrides[get_current_active_user] = override_user
    try:
        resp = client.post(
            f"/api/v1/teams/{team.id}/invites",
            json={"email": "check@test.com", "role": "viewer"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "token" not in data
        assert "token_hash" not in data
        assert "invite_link" in data
        # invite_link contains the token - that's intentional for sharing
        # but the raw token should not appear as a separate field
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
