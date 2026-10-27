"""
Tests for ingest-scoped team API keys (plan task 1.4).

Free (Starter) teams get one ingest-only key so the agent, SDK and CLI can
send data. That key must work on /ingest/* and nowhere else, and rotating it
must never upgrade it to a full-access key.
"""

from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.core.security import _get_team_api_key_by_value
from app.main import app
from app.models.billing import BillingPlan, SubscriptionStatus, TeamSubscription
from app.models.team import Team
from app.models.team_api_key import TeamAPIKey
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
        app.dependency_overrides.pop(get_current_active_user, None)


def _owner_team(db_session: Session, plan: BillingPlan | None = None) -> tuple[User, Team]:
    """Create a team with an owner; no subscription row means Starter."""
    team = Team(name="Scoped Key Team")
    user = User(email="owner@scoped.example", full_name="Owner", hashed_password="hashed", is_active=True)
    db_session.add_all([team, user])
    db_session.commit()
    db_session.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
    if plan is not None:
        db_session.add(
            TeamSubscription(
                team_id=team.id,
                stripe_customer_id="cus_test_scoped",
                status=SubscriptionStatus.ACTIVE,
                plan=plan,
            )
        )
    db_session.commit()
    app.dependency_overrides[get_current_active_user] = lambda: user
    return user, team


def _add_key(db_session: Session, team: Team, scope: str) -> str:
    raw = TeamAPIKey.generate_key()
    db_session.add(TeamAPIKey(team_id=team.id, key_name=f"{scope} key", key_hash=TeamAPIKey.hash_key(raw), scope=scope))
    db_session.commit()
    return raw


def _create_key(client: TestClient, team: Team, scope: str | None):
    body = {"key_name": "agent", "team_id": str(team.id)}
    if scope is not None:
        body["scope"] = scope
    return client.post(f"/api/v1/teams/{team.id}/api-keys", json=body)


USAGE = {"metrics": [{"timestamp": "2026-10-27T00:00:00Z", "provider": "aws", "gpu_type": "a100", "gpu_hours": 1}]}
COST = {"records": [{"date": "2026-10-27", "provider": "aws", "gpu_type": "a100", "cost_usd": 3.5}]}


# ── Creation on the Starter plan ───────────────────────────────────────────────


def test_starter_can_create_one_ingest_key(client, db_session):
    _, team = _owner_team(db_session)

    resp = _create_key(client, team, "ingest")

    assert resp.status_code == 200, resp.text
    assert resp.json()["scope"] == "ingest"
    assert resp.json()["api_key"]


def test_starter_second_ingest_key_hits_limit(client, db_session):
    _, team = _owner_team(db_session)
    assert _create_key(client, team, "ingest").status_code == 200

    resp = _create_key(client, team, "ingest")

    assert resp.status_code == 403
    assert resp.json()["error"] == "limit_reached"


def test_starter_cannot_create_full_access_key(client, db_session):
    _, team = _owner_team(db_session)

    resp = _create_key(client, team, None)  # default scope is full access

    assert resp.status_code == 403
    assert resp.json()["error"] == "plan_required"


def test_growth_full_and_ingest_limits_are_independent(client, db_session):
    _, team = _owner_team(db_session, plan=BillingPlan.GROWTH)

    assert _create_key(client, team, "full").json()["scope"] == "full"
    assert _create_key(client, team, "ingest").json()["scope"] == "ingest"


def test_rotating_an_ingest_key_keeps_it_ingest_only(client, db_session):
    _, team = _owner_team(db_session)
    created = _create_key(client, team, "ingest").json()

    # A Starter team must not be able to escalate scope through rotation
    resp = client.post(
        f"/api/v1/teams/{team.id}/api-keys/{created['id']}/rotate",
        json={"key_name": "agent", "team_id": str(team.id), "scope": "full"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["scope"] == "ingest"


# ── Where an ingest key is accepted ────────────────────────────────────────────


def test_ingest_key_accepted_on_usage_ingest(client, db_session):
    _, team = _owner_team(db_session)
    key = _add_key(db_session, team, "ingest")

    resp = client.post("/api/v1/ingest/usage", json=USAGE, headers={"X-API-Key": key})

    assert resp.status_code == 200, resp.text


def test_ingest_key_accepted_on_cost_ingest(client, db_session):
    _, team = _owner_team(db_session)
    key = _add_key(db_session, team, "ingest")

    resp = client.post("/api/v1/ingest/cost", json=COST, headers={"X-API-Key": key})

    assert resp.status_code == 200, resp.text


def test_ingest_key_rejected_on_read_endpoint(client, db_session):
    _, team = _owner_team(db_session)
    key = _add_key(db_session, team, "ingest")
    today = date.today().isoformat()

    resp = client.get(
        f"/api/v1/analytics/cost/by-model?start={today}&end={today}",
        headers={"X-API-Key": key},
    )

    assert resp.status_code == 403
    assert "ingest" in resp.json()["message"].lower()


def test_full_key_still_reads(client, db_session):
    _, team = _owner_team(db_session, plan=BillingPlan.GROWTH)
    key = _add_key(db_session, team, "full")
    today = date.today().isoformat()

    resp = client.get(
        f"/api/v1/analytics/cost/by-model?start={today}&end={today}",
        headers={"X-API-Key": key},
    )

    assert resp.status_code == 200, resp.text


def test_ingest_key_denied_outside_a_request(db_session):
    """With no request route recorded (Celery, scripts), an ingest key is refused."""
    _, team = _owner_team(db_session)
    key = _add_key(db_session, team, "ingest")

    with pytest.raises(HTTPException) as exc_info:
        _get_team_api_key_by_value(key, db_session, "req-test")

    assert exc_info.value.status_code == 403
