"""
External job IDs are unique per team, on real PostgreSQL.

Covers the jobs uniqueness rule, the ON CONFLICT upsert in JobIngestionService
(identity, idempotency, statistics, concurrency) and the Jobs API conflict
behaviour. Needs a disposable PostgreSQL server: set HELIOX_MIGRATION_TEST_SERVER_URL
(see test_migration_history.py). Each module run creates its own uniquely named
``heliox_jobidtest_*`` database, migrates it to head and drops it.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.job import Job
from app.models.team import Team
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User

BACKEND = Path(__file__).resolve().parents[1]
SERVER_URL = os.environ.get("HELIOX_MIGRATION_TEST_SERVER_URL")

pytestmark = pytest.mark.skipif(not SERVER_URL, reason="HELIOX_MIGRATION_TEST_SERVER_URL not set")

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def pg_url():
    name = f"heliox_jobidtest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(SERVER_URL).set(database=name).render_as_string(hide_password=False)
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "ENV": "dev",
        "SECRET_KEY": os.environ.get("SECRET_KEY", "migration-test-secret-key-at-least-32-chars"),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://127.0.0.1:1/15"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="module")
def engine(pg_url):
    eng = create_engine(pg_url)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


def _team(db, tag):
    team = Team(name=f"jobid-{tag}-{uuid.uuid4().hex[:8]}")
    db.add(team)
    db.commit()
    return team


def _job(team_id, job_id, model_name="llama", status="running"):
    return Job(
        team_id=team_id,
        job_id=job_id,
        model_name=model_name,
        gpu_type="a100",
        provider="aws",
        start_time=START,
        status=status,
    )


def _rows(db, job_id):
    db.expire_all()
    return db.execute(select(Job).where(Job.job_id == job_id).order_by(Job.created_at)).scalars().all()


def _async_url(url):
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


def _job_data(job_id, team_name, model_name="llama-70b", status="running", end_time=None):
    from app.services.job_ingestion import JobData

    return JobData(
        job_id=job_id,
        team_name=team_name,
        model_name=model_name,
        provider="aws",
        gpu_type="a100",
        start_time=START,
        end_time=end_time,
        status=status,
    )


async def _upsert(pg_url, job_data, team_id):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.services.job_ingestion import JobIngestionService

    eng = create_async_engine(_async_url(pg_url))
    try:
        async with AsyncSession(eng, expire_on_commit=False) as session:
            result = await JobIngestionService(session).upsert_job(job_data, team_id)
            await session.commit()
            return result
    finally:
        await eng.dispose()


# ── Uniqueness rule ────────────────────────────────────────────────────────────


def test_two_teams_can_use_the_same_external_id(db):
    a, b = _team(db, "a"), _team(db, "b")
    db.add(_job(a.id, "train-001-shared"))
    db.commit()
    db.add(_job(b.id, "train-001-shared"))
    db.commit()
    assert {j.team_id for j in _rows(db, "train-001-shared")} == {a.id, b.id}


def test_same_team_cannot_reuse_an_external_id(db):
    a = _team(db, "dup")
    db.add(_job(a.id, "train-dup"))
    db.commit()
    db.add(_job(a.id, "train-dup"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert len(_rows(db, "train-dup")) == 1


# ── Ingestion upsert ───────────────────────────────────────────────────────────


async def test_ingestion_for_another_team_never_reassigns_an_existing_job(db, pg_url):
    a, b = _team(db, "owner"), _team(db, "other")
    original = _job(a.id, "train-001-reassign", model_name="tenant-a-model")
    db.add(original)
    db.commit()
    original_id = original.id

    await _upsert(pg_url, _job_data("train-001-reassign", b.name, model_name="tenant-b-model"), b.id)

    rows = _rows(db, "train-001-reassign")
    by_team = {r.team_id: r for r in rows}
    assert len(rows) == 2
    assert by_team[a.id].id == original_id  # A's job: same UUID, same owner, untouched
    assert by_team[a.id].model_name == "tenant-a-model"
    assert by_team[b.id].id != original_id  # B got its own record
    assert by_team[b.id].model_name == "tenant-b-model"


async def test_same_team_retry_updates_the_original_record(db, pg_url):
    a = _team(db, "retry")
    first = await _upsert(pg_url, _job_data("train-retry", a.name, status="running"), a.id)
    row = _rows(db, "train-retry")
    assert len(row) == 1
    original_id, created_at = row[0].id, row[0].created_at

    done = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
    second = await _upsert(pg_url, _job_data("train-retry", a.name, status="completed", end_time=done), a.id)
    rows = _rows(db, "train-retry")
    assert len(rows) == 1
    assert rows[0].id == original_id and rows[0].team_id == a.id
    assert rows[0].created_at == created_at
    # jobs timestamps are TIMESTAMP WITHOUT TIME ZONE, stored as UTC
    assert rows[0].status == "completed" and rows[0].end_time.replace(tzinfo=timezone.utc) == done
    assert first[1] is True and second[1] is False  # inserted, then updated


async def test_concurrent_same_team_upserts_create_one_record(db, pg_url):
    a = _team(db, "race")
    results = await asyncio.gather(*[_upsert(pg_url, _job_data("train-race", a.name), a.id) for _ in range(8)])
    assert len(_rows(db, "train-race")) == 1
    assert sorted(inserted for _, inserted in results) == [False] * 7 + [True]


async def test_concurrent_cross_team_upserts_stay_independent(db, pg_url):
    teams = [_team(db, f"race{i}") for i in range(4)]
    results = await asyncio.gather(*[_upsert(pg_url, _job_data("train-shared-race", t.name), t.id) for t in teams])
    rows = _rows(db, "train-shared-race")
    assert {r.team_id for r in rows} == {t.id for t in teams}
    assert all(inserted for _, inserted in results)


async def test_ingest_jobs_reports_inserts_then_updates_and_leaves_other_tenants_alone(db, pg_url):
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.services.job_ingestion import JobIngestionService

    # An unrelated tenant already uses one of the mock IDs
    outsider = _team(db, "outsider")
    db.add(_job(outsider.id, "job-001", model_name="outsider-model"))
    db.commit()

    eng = create_async_engine(_async_url(pg_url))
    try:
        async with AsyncSession(eng, expire_on_commit=False) as session:
            first = await JobIngestionService(session).ingest_jobs()
        async with AsyncSession(eng, expire_on_commit=False) as session:
            second = await JobIngestionService(session).ingest_jobs()
    finally:
        await eng.dispose()

    total = first["jobs"]["total"]
    assert first["jobs"] == {"inserted": total, "updated": 0, "failed": 0, "total": total}
    assert second["jobs"] == {"inserted": 0, "updated": total, "failed": 0, "total": total}
    assert first["errors"] == [] and second["errors"] == []

    rows = _rows(db, "job-001")
    outsider_rows = [r for r in rows if r.team_id == outsider.id]
    assert len(outsider_rows) == 1 and outsider_rows[0].model_name == "outsider-model"
    assert len(rows) == 2


# ── Jobs API on PostgreSQL ─────────────────────────────────────────────────────


@pytest.fixture
def api(engine, monkeypatch):
    from fastapi.testclient import TestClient

    from app.auth.deps import get_current_active_user
    from app.core.db import get_db
    from app.main import app

    monkeypatch.setattr("app.core.rate_limit.is_rate_limited", lambda *a, **k: (False, 60))
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    setup = Session()
    users, teams = {}, {}
    for tag in ("a", "b"):
        team = Team(name=f"api-{tag}-{uuid.uuid4().hex[:8]}")
        user = User(email=f"api-{tag}-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", is_active=True)
        setup.add_all([team, user])
        setup.flush()
        setup.add(TeamMember(team_id=team.id, user_id=user.id, role=TeamRole.OWNER))
        users[tag], teams[tag] = user, team
    setup.commit()
    current = {"user": users["a"]}

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_active_user] = lambda: current["user"]

    def as_user(tag):
        current["user"] = users[tag]

    yield TestClient(app), as_user, teams
    app.dependency_overrides.clear()
    setup.close()


def _body(team_id, job_id=None):
    body = {"model_name": "m", "gpu_type": "A100", "provider": "aws", "team_id": str(team_id)}
    if job_id:
        body["job_id"] = job_id
    return body


def test_api_two_tenants_can_create_the_same_external_id(api):
    client, as_user, teams = api
    as_user("a")
    a = client.post("/api/v1/jobs/", json=_body(teams["a"].id, "train-001-api"))
    as_user("b")
    b = client.post("/api/v1/jobs/", json=_body(teams["b"].id, "train-001-api"))
    # Tenant B learns nothing about tenant A: the ID is simply free in B's namespace
    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] != b.json()["id"]
    assert client.get(f"/api/v1/jobs/{a.json()['id']}").status_code == 404  # B can't read A's job


def test_api_duplicate_within_a_team_is_409_and_session_survives(api):
    client, as_user, teams = api
    as_user("a")
    assert client.post("/api/v1/jobs/", json=_body(teams["a"].id, "train-dup-api")).status_code == 201
    dup = client.post("/api/v1/jobs/", json=_body(teams["a"].id, "train-dup-api"))
    assert dup.status_code == 409
    assert str(teams["b"].id) not in dup.text
    assert client.get("/api/v1/jobs/").status_code == 200
    generated = client.post("/api/v1/jobs/", json=_body(teams["a"].id))
    assert generated.status_code == 201 and generated.json()["job_id"].startswith("job_")


def test_api_uuid_routes_still_work(api):
    client, as_user, teams = api
    as_user("a")
    created = client.post("/api/v1/jobs/", json=_body(teams["a"].id, "train-uuid-api")).json()
    assert client.get(f"/api/v1/jobs/{created['id']}").json()["job_id"] == "train-uuid-api"
    updated = client.put(f"/api/v1/jobs/{created['id']}", json={"status": "completed"})
    assert updated.status_code == 200 and updated.json()["id"] == created["id"]
    assert client.put(f"/api/v1/jobs/{created['id']}", json={"team_id": str(teams["b"].id)}).status_code == 422
    assert client.delete(f"/api/v1/jobs/{created['id']}").status_code == 204
    assert client.get(f"/api/v1/jobs/{created['id']}").status_code == 404
