"""
Jobs API: creation, tenant-scoped listing, and scoped read/update/delete.

Two tenants with distinct users and jobs. Requests go through the real routes
with the current user overridden, against the isolated SQLite test database.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.main import app
from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User
from app.services.gpu_cost_attribution import attribute_cost_by_model

JOBS = "/api/v1/jobs/"


class World:
    """Two tenants (A, B) plus a user with no team. ``as_user`` switches the caller."""

    def __init__(self, db: Session):
        self.db = db
        self.team_a = Team(name="Tenant A")
        self.team_b = Team(name="Tenant B")
        self.owner_a = self._user("owner-a@example.com")
        self.viewer_a = self._user("viewer-a@example.com")
        self.owner_b = self._user("owner-b@example.com")
        self.outsider = self._user("outsider@example.com")
        db.add_all([self.team_a, self.team_b])
        db.flush()
        db.add_all(
            [
                TeamMember(team_id=self.team_a.id, user_id=self.owner_a.id, role=TeamRole.OWNER),
                TeamMember(team_id=self.team_a.id, user_id=self.viewer_a.id, role=TeamRole.VIEWER),
                TeamMember(team_id=self.team_b.id, user_id=self.owner_b.id, role=TeamRole.OWNER),
            ]
        )
        self.a_running_aws = self._job(self.team_a, "a-run-aws", "running", "aws")
        self.a_done_gcp = self._job(self.team_a, "a-done-gcp", "completed", "gcp")
        self.b_running_aws = self._job(self.team_b, "b-run-aws", "running", "aws")
        self.b_failed_gcp = self._job(self.team_b, "b-fail-gcp", "failed", "gcp")
        db.commit()
        self.current = None
        app.dependency_overrides[get_current_active_user] = lambda: self.current

    def _user(self, email):
        user = User(email=email, full_name=email.split("@")[0], hashed_password="x", is_active=True)
        self.db.add(user)
        self.db.flush()
        return user

    def _job(self, team, job_id, status, provider):
        job = Job(
            job_id=f"{job_id}-{uuid4().hex[:6]}",
            team_id=team.id,
            model_name=f"model-{job_id}",
            gpu_type="a100",
            provider=provider,
            status=status,
            start_time=datetime(2026, 1, 1, 0, 0),
            end_time=datetime(2026, 1, 1, 2, 0) if status != "running" else None,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def as_user(self, user):
        self.current = user
        return self


@pytest.fixture
def client(db_session: Session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def world(db_session, client):
    return World(db_session)


def _ids(resp):
    return {j["id"] for j in resp.json()["jobs"]}


def _create_body(team_id, **overrides):
    body = {"model_name": "bert", "gpu_type": "a100", "provider": "aws", "team_id": str(team_id), "status": "running"}
    body.update(overrides)
    return body


# ── Creation ───────────────────────────────────────────────────────────────────


def test_create_job_without_job_id_returns_201_with_generated_id(client, world):
    world.as_user(world.owner_a)

    resp = client.post(JOBS, json=_create_body(world.team_a.id, start_time="2026-01-02T00:00:00"))

    assert resp.status_code == 201, resp.text
    body = resp.json()
    for field in ("id", "team_id", "job_id", "model_name", "gpu_type", "provider", "status", "start_time", "end_time"):
        assert field in body
    assert body["team_id"] == str(world.team_a.id)
    assert body["job_id"] and len(body["job_id"]) <= 100


def test_create_job_with_explicit_external_job_id(client, world):
    world.as_user(world.owner_a)

    resp = client.post(JOBS, json=_create_body(world.team_a.id, job_id="train-run-42"))

    assert resp.status_code == 201, resp.text
    assert resp.json()["job_id"] == "train-run-42"


def test_duplicate_job_id_in_same_team_is_409_not_500(client, world):
    world.as_user(world.owner_a)
    assert client.post(JOBS, json=_create_body(world.team_a.id, job_id="dup-1")).status_code == 201

    resp = client.post(JOBS, json=_create_body(world.team_a.id, job_id="dup-1"))

    assert resp.status_code == 409


def test_job_id_used_by_another_tenant_is_available_and_reveals_nothing(client, world):
    # External IDs are unique per team: another tenant's ID is simply free here,
    # so the response can't tell the caller that some other tenant uses it
    world.as_user(world.owner_a)
    resp = client.post(JOBS, json=_create_body(world.team_a.id, job_id=world.b_running_aws.job_id))

    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["team_id"] == str(world.team_a.id) and created["id"] != str(world.b_running_aws.id)
    assert str(world.team_b.id) not in resp.text and world.b_running_aws.model_name not in resp.text
    # Tenant B's job is untouched
    world.as_user(world.owner_b)
    theirs = client.get(f"{JOBS}{world.b_running_aws.id}").json()
    assert theirs["team_id"] == str(world.team_b.id) and theirs["model_name"] == world.b_running_aws.model_name


@pytest.mark.parametrize("bad_id", ["", "x" * 101, "has space", "semi;colon"])
def test_invalid_external_job_id_is_422(client, world, bad_id):
    world.as_user(world.owner_a)

    assert client.post(JOBS, json=_create_body(world.team_a.id, job_id=bad_id)).status_code == 422


def test_cannot_create_job_in_another_tenant(client, world):
    world.as_user(world.owner_a)

    assert client.post(JOBS, json=_create_body(world.team_b.id)).status_code in (403, 404)


def test_create_with_end_before_start_is_422(client, world):
    world.as_user(world.owner_a)
    body = _create_body(world.team_a.id, start_time="2026-01-02T05:00:00", end_time="2026-01-02T04:00:00")

    assert client.post(JOBS, json=body).status_code == 422


# ── Listing is always tenant-scoped ────────────────────────────────────────────


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"status": "running"},
        {"provider": "aws"},
        {"status": "running", "provider": "aws"},
        {"status": "failed"},
        {"provider": "gcp"},
    ],
    ids=["none", "status", "provider", "status+provider", "status-only-b-has", "provider-gcp"],
)
def test_listing_never_returns_other_tenants_jobs(client, world, params):
    world.as_user(world.owner_a)

    resp = client.get(JOBS, params=params)

    assert resp.status_code == 200
    b_ids = {str(world.b_running_aws.id), str(world.b_failed_gcp.id)}
    assert not (_ids(resp) & b_ids)
    # Counts must not include other tenants either
    assert resp.json()["total"] == len(_ids(resp))


def test_status_filter_returns_only_own_matching_jobs(client, world):
    world.as_user(world.owner_a)

    resp = client.get(JOBS, params={"status": "running"})

    assert _ids(resp) == {str(world.a_running_aws.id)}
    assert resp.json()["total"] == 1


def test_provider_filter_returns_only_own_matching_jobs(client, world):
    world.as_user(world.owner_a)

    resp = client.get(JOBS, params={"provider": "aws"})

    assert _ids(resp) == {str(world.a_running_aws.id)}


@pytest.mark.parametrize(
    "extra,expected",
    [({}, 2), ({"status": "running"}, 1), ({"provider": "gcp"}, 1), ({"status": "completed", "provider": "gcp"}, 1)],
)
def test_team_id_combined_with_filters(client, world, extra, expected):
    world.as_user(world.owner_a)

    resp = client.get(JOBS, params={"team_id": str(world.team_a.id), **extra})

    assert resp.status_code == 200
    assert resp.json()["total"] == expected == len(resp.json()["jobs"])


def test_filtering_by_another_tenants_team_id_is_denied(client, world):
    world.as_user(world.owner_a)

    resp = client.get(JOBS, params={"team_id": str(world.team_b.id), "status": "running"})

    assert resp.status_code == 403
    assert "jobs" not in resp.json()


def test_pagination_and_counts_are_scoped(client, world):
    world.as_user(world.owner_a)

    page1 = client.get(JOBS, params={"limit": 1, "skip": 0}).json()
    page2 = client.get(JOBS, params={"limit": 1, "skip": 1}).json()

    assert page1["total"] == page2["total"] == 2
    assert page1["has_more"] is True and page2["has_more"] is False
    assert {j["id"] for j in page1["jobs"] + page2["jobs"]} == {str(world.a_running_aws.id), str(world.a_done_gcp.id)}


def test_user_without_teams_sees_no_jobs(client, world):
    world.as_user(world.outsider)

    for params in ({}, {"status": "running"}, {"provider": "aws"}):
        resp = client.get(JOBS, params=params)
        assert resp.status_code == 200
        assert resp.json()["jobs"] == [] and resp.json()["total"] == 0


def test_invalid_status_filter_is_422(client, world):
    world.as_user(world.owner_a)

    assert client.get(JOBS, params={"status": "bogus"}).status_code == 422


# ── Read / update / delete ─────────────────────────────────────────────────────


def test_read_own_job_and_not_another_tenants(client, world):
    world.as_user(world.owner_a)

    assert client.get(f"{JOBS}{world.a_running_aws.id}").status_code == 200
    assert client.get(f"{JOBS}{world.b_running_aws.id}").status_code == 404


def test_viewer_can_read_own_team_job(client, world):
    world.as_user(world.viewer_a)

    assert client.get(f"{JOBS}{world.a_running_aws.id}").status_code == 200


def test_owner_completes_running_job(client, world):
    world.as_user(world.owner_a)

    resp = client.put(
        f"{JOBS}{world.a_running_aws.id}", json={"status": "completed", "end_time": "2026-01-01T06:00:00"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    assert resp.json()["end_time"].startswith("2026-01-01T06:00:00")


def test_update_end_before_start_is_422(client, world):
    world.as_user(world.owner_a)

    resp = client.put(f"{JOBS}{world.a_running_aws.id}", json={"end_time": "2025-12-31T00:00:00"})

    assert resp.status_code == 422


def test_update_cannot_change_team(client, world, db_session):
    world.as_user(world.owner_a)

    resp = client.put(f"{JOBS}{world.a_running_aws.id}", json={"team_id": str(world.team_b.id)})

    assert resp.status_code == 422
    db_session.refresh(world.a_running_aws)
    assert world.a_running_aws.team_id == world.team_a.id


def test_cannot_update_or_delete_another_tenants_job(client, world, db_session):
    world.as_user(world.owner_a)

    assert client.put(f"{JOBS}{world.b_running_aws.id}", json={"status": "failed"}).status_code == 404
    assert client.delete(f"{JOBS}{world.b_running_aws.id}").status_code == 404
    db_session.refresh(world.b_running_aws)
    assert world.b_running_aws.status == "running"


def test_viewer_cannot_mutate_jobs(client, world):
    world.as_user(world.viewer_a)

    assert client.post(JOBS, json=_create_body(world.team_a.id)).status_code == 403
    assert client.put(f"{JOBS}{world.a_running_aws.id}", json={"status": "failed"}).status_code == 403
    assert client.delete(f"{JOBS}{world.a_running_aws.id}").status_code == 403


def test_owner_deletes_own_job(client, world, db_session):
    world.as_user(world.owner_a)
    job_id = world.a_done_gcp.id

    assert client.delete(f"{JOBS}{job_id}").status_code == 204
    assert client.get(f"{JOBS}{job_id}").status_code == 404


def test_missing_and_malformed_job_ids(client, world):
    world.as_user(world.owner_a)

    assert client.get(f"{JOBS}{uuid4()}").status_code == 404
    assert client.get(f"{JOBS}not-a-uuid").status_code == 422
    assert client.put(f"{JOBS}{uuid4()}", json={"status": "failed"}).status_code == 404


def test_unauthenticated_requests_are_rejected(client):
    assert client.get(JOBS).status_code == 401
    assert client.post(JOBS, json={}).status_code == 401
    assert client.get(f"{JOBS}{uuid4()}").status_code == 401
    assert client.put(f"{JOBS}{uuid4()}", json={"status": "failed"}).status_code == 401
    assert client.delete(f"{JOBS}{uuid4()}").status_code == 401


# ── Jobs created through the API feed cost attribution ─────────────────────────


def test_api_created_jobs_participate_in_attribution(client, world, db_session):
    world.as_user(world.owner_a)
    # H100 so the fixture's still-running A100 job (which counts up to now) can't overlap
    run = client.post(
        JOBS,
        json=_create_body(world.team_a.id, model_name="llama", gpu_type="h100", start_time="2026-02-01T00:00:00"),
    ).json()
    done = client.put(f"{JOBS}{run['id']}", json={"status": "completed", "end_time": "2026-02-01T12:00:00"})
    assert done.status_code == 200, done.text
    other = client.post(
        JOBS,
        json=_create_body(
            world.team_a.id,
            model_name="bert",
            gpu_type="h100",
            start_time="2026-02-01T06:00:00",
            end_time="2026-02-01T12:00:00",
        ),
    )
    assert other.status_code == 201, other.text
    db_session.add(
        CostSnapshot(
            team_id=world.team_a.id, date=date(2026, 2, 1), provider="aws", gpu_type="h100", cost_usd=Decimal("180")
        )
    )
    db_session.add(
        CostSnapshot(
            team_id=world.team_b.id, date=date(2026, 2, 1), provider="aws", gpu_type="h100", cost_usd=Decimal("999")
        )
    )
    db_session.commit()

    result = attribute_cost_by_model(db_session, world.team_a.id, date(2026, 2, 1), date(2026, 2, 1))

    costs = {m.model_name: round(m.cost_usd, 2) for m in result.models}
    # llama ran 12h, bert 6h on the same A100 day: $180 split 2:1; tenant B's $999 is excluded
    assert costs["llama"] == 120.0 and costs["bert"] == 60.0
    # The fixture's still-running A100 job is listed at $0 (no A100 spend that day); spend is conserved
    assert sum(costs.values()) == pytest.approx(180.0)
    assert result.total_usd == pytest.approx(180.0)
    assert result.unattributed_usd == pytest.approx(0.0)
