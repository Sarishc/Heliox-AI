"""Usage tracking helpers."""

from datetime import date
from uuid import UUID

from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.api_usage import ApiUsage


def record_api_usage(db: Session, *, team_id: UUID, endpoint: str) -> None:
    today = date.today()
    stmt = insert(ApiUsage).values(team_id=team_id, date=today, endpoint=endpoint, count=1)
    stmt = stmt.on_conflict_do_update(
        index_elements=["team_id", "date", "endpoint"],
        set_={"count": ApiUsage.count + 1},
    )
    try:
        db.execute(stmt)
        db.commit()
    except OperationalError:
        # Fallback for SQLite or missing unique constraint in test environments
        existing = (
            db.query(ApiUsage)
            .filter(
                ApiUsage.team_id == team_id,
                ApiUsage.date == today,
                ApiUsage.endpoint == endpoint,
            )
            .first()
        )
        if existing:
            existing.count += 1
        else:
            db.add(ApiUsage(team_id=team_id, date=today, endpoint=endpoint, count=1))
        db.commit()
