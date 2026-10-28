"""
Alembic history regression tests.

The graph tests read migration files only and always run. The upgrade tests
need a disposable PostgreSQL server: set HELIOX_MIGRATION_TEST_SERVER_URL to
an admin URL (e.g. postgresql+psycopg2://postgres:postgres@localhost:5432/postgres).
Each test creates its own uniquely named ``heliox_migtest_*`` database, runs
Alembic in a subprocess against it, and drops it; no other database is touched.
"""

import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
SERVER_URL = os.environ.get("HELIOX_MIGRATION_TEST_SERVER_URL")
if os.environ.get("HELIOX_REQUIRE_POSTGRES_TESTS") == "1" and not SERVER_URL:
    # CI sets this so the upgrade tests fail loudly instead of silently skipping
    raise RuntimeError("HELIOX_REQUIRE_POSTGRES_TESTS=1 but HELIOX_MIGRATION_TEST_SERVER_URL is not set")


def _script() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


# ── Graph (always runs) ────────────────────────────────────────────────────────


def test_history_has_exactly_one_head():
    assert _script().get_heads() == ["037"]


def test_tenant_scoped_job_ids_follow_the_merge():
    assert _script().get_revision("037").down_revision == "036"


def test_merge_revision_joins_scope_and_usage_branches():
    assert _script().get_revision("036").down_revision == ("033", "035")


def test_merged_migrations_keep_their_original_parents():
    # Already-applied migrations must not be re-parented; 036 only adds a merge
    script = _script()
    assert script.get_revision("033").down_revision == "032"
    assert script.get_revision("034").down_revision == "032"
    assert script.get_revision("035").down_revision == "034"


def test_merge_revision_changes_no_schema():
    path = next((BACKEND / "alembic" / "versions").glob("036_*.py"))
    spec = importlib.util.spec_from_file_location("migration_036", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Any schema operation would need an Alembic context and fail here
    assert module.upgrade() is None
    assert module.downgrade() is None


# ── Upgrades against a disposable PostgreSQL database ──────────────────────────

needs_postgres = pytest.mark.skipif(not SERVER_URL, reason="HELIOX_MIGRATION_TEST_SERVER_URL not set")


@pytest.fixture
def scratch_db_url():
    name = f"heliox_migtest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(SERVER_URL).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "ENV": "dev",
        "SECRET_KEY": os.environ.get("SECRET_KEY", "migration-test-secret-key-at-least-32-chars"),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/15"),
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True
    )


def _alembic(db_url: str, *args: str) -> None:
    result = _run_alembic(db_url, *args)
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr[-2000:]}"


def _assert_final_schema(db_url: str) -> None:
    engine = create_engine(db_url)
    try:
        insp = inspect(engine)
        keys = {c["name"]: c for c in insp.get_columns("team_api_keys")}
        assert "scope" in keys and keys["scope"]["nullable"] is False
        assert "full" in str(keys["scope"]["default"])

        usage = {c["name"]: c for c in insp.get_columns("usage_snapshots")}
        assert (usage["gpu_hours"]["type"].precision, usage["gpu_hours"]["type"].scale) == (14, 6)
        allocated = usage["allocated_gpu_hours"]
        assert (allocated["type"].precision, allocated["type"].scale) == (14, 6)
        assert allocated["nullable"] is False

        job_indexes = _job_indexes(engine)
        assert job_indexes["uq_jobs_team_id_job_id"] == (True, ["team_id", "job_id"])
        assert "ix_jobs_job_id" not in job_indexes

        assert _version(engine) == ["037"]
    finally:
        engine.dispose()


def _version(engine) -> list:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()


def _job_indexes(engine) -> dict:
    return {ix["name"]: (bool(ix["unique"]), ix["column_names"]) for ix in inspect(engine).get_indexes("jobs")}


def _seed_jobs(engine, rows):
    """Insert (team_name, job_id) jobs with plain SQL; returns {(team_name, job_id): (id, team_id, created_at)}."""
    seeded = {}
    with engine.begin() as conn:
        teams = {}
        for team_name, job_id in rows:
            if team_name not in teams:
                teams[team_name] = conn.execute(
                    text("INSERT INTO teams (id, name) VALUES (:id, :name) RETURNING id"),
                    {"id": uuid.uuid4(), "name": f"{team_name}-{uuid.uuid4().hex[:6]}"},
                ).scalar_one()
            seeded[(team_name, job_id)] = conn.execute(
                text(
                    "INSERT INTO jobs (id, job_id, team_id, model_name, gpu_type, provider, status) "
                    "VALUES (:id, :job_id, :team_id, 'llama', 'a100', 'aws', 'running') "
                    "RETURNING id, team_id, created_at"
                ),
                {"id": uuid.uuid4(), "job_id": job_id, "team_id": teams[team_name]},
            ).one()
    return seeded


def _all_jobs(engine):
    with engine.connect() as conn:
        return {
            tuple(r) for r in conn.execute(text("SELECT id, team_id, job_id, created_at FROM jobs ORDER BY id")).all()
        }


@needs_postgres
def test_fresh_database_upgrades_to_head(scratch_db_url):
    _alembic(scratch_db_url, "upgrade", "head")
    _assert_final_schema(scratch_db_url)


@needs_postgres
@pytest.mark.parametrize(
    "existing_state",
    [["033"], ["034"], ["035"], ["033", "034"]],
    ids=["main-at-033", "main-at-034", "pr10-at-035", "both-heads"],
)
def test_existing_database_states_upgrade_to_head(scratch_db_url, existing_state):
    # Reproduce a database that applied the old branches, then upgrade it
    for revision in existing_state:
        _alembic(scratch_db_url, "upgrade", revision)
    _alembic(scratch_db_url, "upgrade", "head")
    _assert_final_schema(scratch_db_url)


# ── 037: tenant-scoped external job IDs ────────────────────────────────────────


@needs_postgres
def test_036_database_with_jobs_upgrades_to_037_and_keeps_every_row(scratch_db_url):
    _alembic(scratch_db_url, "upgrade", "036")
    engine = create_engine(scratch_db_url)
    try:
        _seed_jobs(engine, [("team-a", "train-001"), ("team-a", "train-002"), ("team-b", "train-003")])
        before = _all_jobs(engine)

        _alembic(scratch_db_url, "upgrade", "head")

        assert _all_jobs(engine) == before  # same UUIDs, owners, IDs and timestamps
        assert _job_indexes(engine)["uq_jobs_team_id_job_id"] == (True, ["team_id", "job_id"])
        assert "ix_jobs_job_id" not in _job_indexes(engine)
        assert _version(engine) == ["037"]

        # Another team may now reuse an ID; the same team still may not
        _seed_jobs(engine, [("team-c", "train-001")])
        team_a = next(team_id for (_id, team_id, job_id, _created) in before if job_id == "train-001")
        with pytest.raises(Exception, match="uq_jobs_team_id_job_id"):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO jobs (id, job_id, team_id, model_name, gpu_type, provider, status) "
                        "VALUES (:id, 'train-001', :team, 'x', 'a100', 'aws', 'running')"
                    ),
                    {"id": uuid.uuid4(), "team": team_a},
                )
    finally:
        engine.dispose()


@needs_postgres
def test_downgrade_with_cross_team_duplicates_is_refused_without_changes(scratch_db_url):
    _alembic(scratch_db_url, "upgrade", "head")
    engine = create_engine(scratch_db_url)
    try:
        _seed_jobs(engine, [("team-a", "shared-001"), ("team-b", "shared-001"), ("team-a", "solo-002")])
        before = _all_jobs(engine)

        result = _run_alembic(scratch_db_url, "downgrade", "036")

        assert result.returncode != 0
        assert "037 downgrade refused: 1 external job_id value(s)" in result.stderr
        assert _all_jobs(engine) == before  # nothing deleted, renamed or merged
        assert _version(engine) == ["037"]
        assert "uq_jobs_team_id_job_id" in _job_indexes(engine)
    finally:
        engine.dispose()


@needs_postgres
def test_downgrade_without_collisions_restores_global_uniqueness(scratch_db_url):
    _alembic(scratch_db_url, "upgrade", "head")
    engine = create_engine(scratch_db_url)
    try:
        _seed_jobs(engine, [("team-a", "a-001"), ("team-b", "b-001")])
        before = _all_jobs(engine)

        _alembic(scratch_db_url, "downgrade", "036")
        assert _all_jobs(engine) == before
        assert _job_indexes(engine)["ix_jobs_job_id"] == (True, ["job_id"])
        assert "uq_jobs_team_id_job_id" not in _job_indexes(engine)
        assert _version(engine) == ["036"]

        _alembic(scratch_db_url, "upgrade", "head")
        assert _all_jobs(engine) == before
        assert _version(engine) == ["037"]
    finally:
        engine.dispose()


@needs_postgres
def test_037_refuses_an_unexpected_schema_without_changes(scratch_db_url):
    _alembic(scratch_db_url, "upgrade", "036")
    engine = create_engine(scratch_db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP INDEX ix_jobs_job_id"))
            conn.execute(text("CREATE INDEX ix_jobs_job_id ON jobs (job_id)"))  # not unique

        result = _run_alembic(scratch_db_url, "upgrade", "head")

        assert result.returncode != 0
        assert "037: expected ix_jobs_job_id to be a unique index" in result.stderr
        assert _version(engine) == ["036"]
        assert "uq_jobs_team_id_job_id" not in _job_indexes(engine)
    finally:
        engine.dispose()
