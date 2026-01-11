"""Database connection and session management with SQLAlchemy 2.0."""
import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import get_settings

# Import Base from models to ensure all models are registered
from app.models.base import Base  # noqa: F401

settings = get_settings()
logger = logging.getLogger(__name__)


# Create engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections before using them
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=settings.LOG_LEVEL == "DEBUG",  # Log SQL queries in debug mode
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
            extra={"error_type": type(e).__name__}
        )
        return False

