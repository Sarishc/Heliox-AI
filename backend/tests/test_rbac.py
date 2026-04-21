"""Tests for RBAC (Role-Based Access Control) enforcement."""

import pytest

from fastapi import HTTPException

from app.core.tenant import require_team_access
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User


def test_require_team_access_rejects_non_member(db_session):
    """User not in team gets 403."""
    team = Team(name="Test Team")
    user = User(email="user@test.com", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        require_team_access(db_session, user=user, team_id=team.id)
    assert exc.value.status_code == 403
    assert "not a member" in exc.value.detail.lower()


def test_require_team_access_rejects_viewer_for_admin_ops(db_session):
    """VIEWER role is rejected when allowed_roles=[OWNER, ADMIN]."""
    team = Team(name="Test Team")
    user = User(email="viewer@test.com", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()

    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.VIEWER))
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        require_team_access(
            db_session,
            user=user,
            team_id=team.id,
            allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
        )
    assert exc.value.status_code == 403
    assert "Insufficient role" in exc.value.detail


def test_require_team_access_allows_owner(db_session):
    """OWNER is allowed for admin operations."""
    team = Team(name="Test Team")
    user = User(email="owner@test.com", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()

    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.commit()

    membership = require_team_access(
        db_session,
        user=user,
        team_id=team.id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    assert membership.role == TeamRole.OWNER


def test_require_team_access_allows_admin(db_session):
    """ADMIN is allowed for admin operations."""
    team = Team(name="Test Team")
    user = User(email="admin@test.com", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()

    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.ADMIN))
    db_session.commit()

    membership = require_team_access(
        db_session,
        user=user,
        team_id=team.id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    assert membership.role == TeamRole.ADMIN


def test_require_team_access_allows_any_role_when_no_restriction(db_session):
    """VIEWER is allowed when allowed_roles is None (any member)."""
    team = Team(name="Test Team")
    user = User(email="viewer@test.com", hashed_password="x", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()

    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.VIEWER))
    db_session.commit()

    membership = require_team_access(db_session, user=user, team_id=team.id)
    assert membership.role == TeamRole.VIEWER


def test_require_team_access_cross_tenant_rejected(db_session):
    """User in team A cannot access team B."""
    team_a = Team(name="Team A")
    team_b = Team(name="Team B")
    user = User(email="user@test.com", hashed_password="x", is_active=True)
    db_session.add_all([team_a, team_b, user])
    db_session.commit()

    db_session.add(TeamMember(team_id=team_a.id, user_id=user.id, role=TeamRole.OWNER))
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        require_team_access(
            db_session,
            user=user,
            team_id=team_b.id,
            allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
        )
    assert exc.value.status_code == 403
