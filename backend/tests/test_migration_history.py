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


def _script() -> ScriptDirectory:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(cfg)


# ── Graph (always runs) ────────────────────────────────────────────────────────


def test_history_has_exactly_one_head():
    assert _script().get_heads() == ["036"]


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


def _alembic(db_url: str, *args: str) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "ENV": "dev",
        "SECRET_KEY": os.environ.get("SECRET_KEY", "migration-test-secret-key-at-least-32-chars"),
        "REDIS_URL": os.environ.get("REDIS_URL", "redis://localhost:6379/15"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True
    )
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

        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all() == ["036"]
    finally:
        engine.dispose()


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
