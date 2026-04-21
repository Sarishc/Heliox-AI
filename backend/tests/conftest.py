"""Pytest fixtures for database sessions."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base

# Ensure all models are registered before create_all (e.g. team_invites)
import app.models  # noqa: F401

# SQLite doesn't know how to compile PostgreSQL ARRAY or JSONB columns.
# Patch the SQLite type compiler so tests that use db_session don't error
# on CREATE TABLE.  This is test-only — production always uses Postgres.
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler  # noqa: E402


def _sqlite_visit_array(self, type_, **kw):
    return "TEXT"


def _sqlite_visit_JSONB(self, type_, **kw):
    return "TEXT"


SQLiteTypeCompiler.visit_ARRAY = _sqlite_visit_array  # type: ignore[attr-defined]
SQLiteTypeCompiler.visit_JSONB = _sqlite_visit_JSONB  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def db_engine():
    os.environ["ENV"] = "dev"
    os.environ.setdefault(
        "SECRET_KEY",
        "test-secret-key-at-least-32-characters-long-for-pytest",
    )
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Provide a test DB session that rolls back all changes after each test.

    Tables are created once per session (in db_engine); each test runs inside a
    SAVEPOINT that is rolled back on teardown.  This avoids the drop_all /
    create_all cycle, which hits SQLite's duplicate-index bug when a column
    has both index=True and an explicit Index() with the same generated name.
    """
    connection = db_engine.connect()
    # Begin a SAVEPOINT so we can rollback without touching the schema.
    transaction = connection.begin_nested()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
