"""Pytest fixtures for database sessions."""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base

# Ensure all models are registered before create_all (e.g. team_invites)
import app.models  # noqa: F401


@pytest.fixture(scope="session")
def db_engine():
    os.environ["ENV"] = "dev"
    os.environ.setdefault(
        "SECRET_KEY",
        "test-secret-key-at-least-32-characters-long-for-pytest",
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    # Reset schema per test to avoid cross-test contamination
    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
