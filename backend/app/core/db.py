"""Database connection and session management with SQLAlchemy 2.0."""

import logging
import time
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import get_settings

# Import Base from models to ensure all models are registered
from app.models.base import Base  # noqa: F401

settings = get_settings()
logger = logging.getLogger(__name__)
SLOW_SQL_THRESHOLD_MS = 200


# Create engine with connection pooling (optimized for 100 concurrent users)
# pool_size=20 + max_overflow=30 = 50 max connections per worker
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=settings.LOG_LEVEL == "DEBUG",  # Log SQL queries in debug mode
)


# Slow query profiling: log SQL exceeding 200ms
@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    if conn.info.get("query_start_time"):
        elapsed_ms = (time.perf_counter() - conn.info["query_start_time"].pop()) * 1000
        if elapsed_ms > SLOW_SQL_THRESHOLD_MS:
            stmt_preview = (statement[:200] + "…") if len(statement) > 200 else statement
            logger.warning(
                f"SLOW SQL ({elapsed_ms:.0f}ms): {stmt_preview}",
                extra={"duration_ms": round(elapsed_ms), "sql_preview": stmt_preview},
            )


# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.

    Yields:
        Session: SQLAlchemy database session

    Example:
        @app.get("/items/")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """
    Check if database connection is healthy.

    Returns:
        bool: True if connection is healthy, False otherwise

    This performs a simple SELECT 1 query to verify the connection.
    Safe to use in health check endpoints.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as e:
        # Log database connection failure with warning level
        logger.warning(
            f"Database connection check failed: {type(e).__name__}",
            exc_info=True,
            extra={"error_type": type(e).__name__},
        )
        return False
