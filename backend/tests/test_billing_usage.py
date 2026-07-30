"""Tests for billing usage API."""

from datetime import date, datetime, timedelta, timezone

import pytest

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.core.db import get_db
from app.models.team import Team
from app.models.team_api_key import TeamAPIKey
from app.models.usage import UsageDailyRollup, UsageEventType


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
def team_with_api_key(db_session: Session) -> tuple[Team, str]:
    """Create team and API key."""
    team = Team(name="Usage Test Team")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    raw_key = "sk_test_usage_12345"
    api_key = TeamAPIKey(
        team_id=team.id,
        key_name="test-key",
        key_hash=TeamAPIKey.hash_key(raw_key),
        is_active=True,
    )
    db_session.add(api_key)
    db_session.commit()

    return team, raw_key


def test_usage_summary_empty_returns_zero_totals(client: TestClient, team_with_api_key):
    """Empty usage returns valid structure with zero totals."""
    team, api_key = team_with_api_key

    resp = client.get(
        "/api/v1/billing/usage",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == str(team.id)
    assert "start_date" in data
    assert "end_date" in data
    assert data["totals"]["api_requests"] == 0
    assert data["totals"]["ingestion_line_items"] == 0
    assert data["totals"]["seats"] == 0
    assert data["totals"]["gpu_nodes"] == 0
    assert data["breakdown"] == []
    assert data["daily_summary"] == []


def test_usage_summary_with_rollup_data(client: TestClient, team_with_api_key, db_session: Session):
    """Usage summary returns aggregated data from rollups."""
    team, api_key = team_with_api_key

    today = date.today()
    db_session.add(
        UsageDailyRollup(
            team_id=team.id,
            date=today,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=100,
        )
    )
    db_session.add(
        UsageDailyRollup(
            team_id=team.id,
            date=today,
            event_type=UsageEventType.INGESTION,
            total_quantity=50,
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/v1/billing/usage",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == str(team.id)
    assert data["totals"]["api_requests"] == 100
    assert data["totals"]["ingestion_line_items"] == 50
    assert len(data["breakdown"]) == 2
    assert len(data["daily_summary"]) == 1
    assert data["daily_summary"][0]["api_requests"] == 100
    assert data["daily_summary"][0]["ingestion_line_items"] == 50


def test_usage_summary_date_range(client: TestClient, team_with_api_key):
    """Usage summary accepts from/to date params."""
    team, api_key = team_with_api_key
    from_date = (date.today() - timedelta(days=7)).isoformat()
    to_date = date.today().isoformat()

    resp = client.get(
        f"/api/v1/billing/usage?from={from_date}&to={to_date}",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["start_date"] == from_date
    assert data["end_date"] == to_date


def test_usage_summary_invalid_date_range(client: TestClient, team_with_api_key):
    """Usage summary rejects from > to."""
    api_key = team_with_api_key[1]
    from_date = date.today().isoformat()
    to_date = (date.today() - timedelta(days=7)).isoformat()

    resp = client.get(
        f"/api/v1/billing/usage?from={from_date}&to={to_date}",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 400


def test_usage_summary_requires_auth(client: TestClient, team_with_api_key):
    """Usage summary returns 401 without API key or session."""
    resp = client.get("/api/v1/billing/usage")
    assert resp.status_code == 401


def test_current_month_usage(client: TestClient, team_with_api_key):
    """Current month endpoint returns usage for this month."""
    team, api_key = team_with_api_key

    resp = client.get(
        "/api/v1/billing/usage/current-month",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == str(team.id)
    utc_today = datetime.now(timezone.utc).date()
    first_day = utc_today.replace(day=1)
    assert data["start_date"] == first_day.isoformat()
    assert data["end_date"] == utc_today.isoformat()


def test_usage_tenant_scoping(client: TestClient, db_session: Session):
    """Team A cannot see Team B's usage."""
    team_a = Team(name="Team A")
    team_b = Team(name="Team B")
    db_session.add_all([team_a, team_b])
    db_session.commit()
    db_session.refresh(team_a)
    db_session.refresh(team_b)

    key_a = "sk_team_a_key"
    key_b = "sk_team_b_key"

    api_key_a = TeamAPIKey(
        team_id=team_a.id,
        key_name="team-a-key",
        key_hash=TeamAPIKey.hash_key(key_a),
        is_active=True,
    )
    api_key_b = TeamAPIKey(
        team_id=team_b.id,
        key_name="team-b-key",
        key_hash=TeamAPIKey.hash_key(key_b),
        is_active=True,
    )
    db_session.add_all([api_key_a, api_key_b])
    db_session.commit()

    # Team B has usage
    today = date.today()
    db_session.add(
        UsageDailyRollup(
            team_id=team_b.id,
            date=today,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=999,
        )
    )
    db_session.commit()

    # Team A requests usage - should see 0, not Team B's 999
    resp = client.get(
        "/api/v1/billing/usage",
        headers={"X-API-Key": key_a},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == str(team_a.id)
    assert data["totals"]["api_requests"] == 0
