"""
Cross-tenant security tests.

Ensures Tenant A cannot access Tenant B data.
Must return 404 without leaking existence.
"""
import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.db import get_db
from app.models.cost import CostSnapshot
from app.models.team import Team
from app.models.team_api_key import TeamAPIKey


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
def team_a(db_session: Session) -> tuple[Team, TeamAPIKey]:
    """Create Team A with API key."""
    team = Team(name="Team A")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    raw_key = TeamAPIKey.generate_key()
    api_key = TeamAPIKey(
        team_id=team.id,
        key_name="Key A",
        key_hash=TeamAPIKey.hash_key(raw_key),
        is_active=True,
    )
    db_session.add(api_key)
    db_session.commit()
    return team, raw_key


@pytest.fixture
def team_b(db_session: Session) -> tuple[Team, TeamAPIKey]:
    """Create Team B with API key."""
    team = Team(name="Team B")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    raw_key = TeamAPIKey.generate_key()
    api_key = TeamAPIKey(
        team_id=team.id,
        key_name="Key B",
        key_hash=TeamAPIKey.hash_key(raw_key),
        is_active=True,
    )
    db_session.add(api_key)
    db_session.commit()
    return team, raw_key


@pytest.fixture
def cost_snapshot_team_a(db_session: Session, team_a: tuple[Team, TeamAPIKey]) -> CostSnapshot:
    """Create cost snapshot for Team A."""
    team, _ = team_a
    snap = CostSnapshot(
        team_id=team.id,
        date=date.today(),
        provider="aws",
        gpu_type="A100",
        cost_usd=Decimal("100.00"),
    )
    db_session.add(snap)
    db_session.commit()
    db_session.refresh(snap)
    return snap


def test_team_b_cannot_access_team_a_cost_snapshot(
    client: TestClient,
    team_a: tuple[Team, TeamAPIKey],
    team_b: tuple[Team, TeamAPIKey],
    cost_snapshot_team_a: CostSnapshot,
) -> None:
    """Tenant B attempts to access Tenant A cost snapshot - must return 404."""
    _, key_a = team_a
    _, key_b = team_b
    snapshot_id = cost_snapshot_team_a.id

    # Team B tries to read Team A's cost snapshot
    resp = client.get(
        f"/api/v1/costs/{snapshot_id}",
        headers={"X-API-Key": key_b},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json().get("detail", "").lower()

    # Team B tries to delete Team A's cost snapshot
    resp = client.delete(
        f"/api/v1/costs/{snapshot_id}",
        headers={"X-API-Key": key_b},
    )
    assert resp.status_code == 404

    # Verify Team A's data is still there (Team B's delete did nothing)
    resp = client.get(
        f"/api/v1/costs/{snapshot_id}",
        headers={"X-API-Key": key_a},
    )
    assert resp.status_code == 200


def test_team_a_can_access_own_cost_snapshot(
    client: TestClient,
    team_a: tuple[Team, TeamAPIKey],
    cost_snapshot_team_a: CostSnapshot,
) -> None:
    """Tenant A can access own cost snapshot."""
    _, key_a = team_a
    resp = client.get(
        f"/api/v1/costs/{cost_snapshot_team_a.id}",
        headers={"X-API-Key": key_a},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(cost_snapshot_team_a.id)


def test_nonexistent_id_returns_404(
    client: TestClient,
    team_a: tuple[Team, TeamAPIKey],
) -> None:
    """Accessing non-existent ID returns 404 (no info leak)."""
    _, key_a = team_a
    fake_id = uuid4()
    resp = client.get(
        f"/api/v1/costs/{fake_id}",
        headers={"X-API-Key": key_a},
    )
    assert resp.status_code == 404
