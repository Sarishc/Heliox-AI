"""Pytest fixtures for database sessions."""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base


@pytest.fixture(scope="session")
def db_engine():
    os.environ["ENV"] = "dev"
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
