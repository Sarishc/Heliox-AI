"""
Helpers for tests that need disposable PostgreSQL databases.

Set HELIOX_MIGRATION_TEST_SERVER_URL to an admin URL of a throwaway server. Every database is
uniquely named (prefix given by the caller) and dropped afterwards; no other database is touched.
With HELIOX_REQUIRE_POSTGRES_TESTS=1 (CI) a missing server URL is an error, never a skip.
"""

import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
SERVER_URL = os.environ.get("HELIOX_MIGRATION_TEST_SERVER_URL")
if os.environ.get("HELIOX_REQUIRE_POSTGRES_TESTS") == "1" and not SERVER_URL:
    raise RuntimeError("HELIOX_REQUIRE_POSTGRES_TESTS=1 but HELIOX_MIGRATION_TEST_SERVER_URL is not set")

needs_postgres = pytest.mark.skipif(not SERVER_URL, reason="HELIOX_MIGRATION_TEST_SERVER_URL not set")


def admin_engine():
    return create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")


@contextmanager
def scratch_database(prefix: str):
    """Yield the URL of a new, empty database; drop it afterwards."""
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(SERVER_URL).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
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


def alembic(db_url: str, *args: str) -> None:
    result = run_alembic(db_url, *args)
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr[-3000:]}"


def alembic_version(engine) -> list[str]:
    with engine.connect() as conn:
        return sorted(r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version")))
