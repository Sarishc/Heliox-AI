"""Rollup computations for team metrics."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.team_rollup import TeamDailyRollup


def compute_daily_rollup(db: Session, *, team_id: UUID, target_date: date) -> None:
    total_cost = (
        db.execute(
            select(func.sum(CostSnapshot.cost_usd)).where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date == target_date,
            )
        ).scalar_one_or_none()
        or 0
    )
    total_usage = (
        db.execute(
            select(func.sum(UsageSnapshot.gpu_hours)).where(
                UsageSnapshot.team_id == team_id,
                UsageSnapshot.date == target_date,
            )
        ).scalar_one_or_none()
        or 0
    )

    stmt = insert(TeamDailyRollup).values(
        team_id=team_id,
        date=target_date,
        total_cost_usd=Decimal(total_cost),
        total_gpu_hours=Decimal(total_usage),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["team_id", "date"],
        set_={
            "total_cost_usd": stmt.excluded.total_cost_usd,
            "total_gpu_hours": stmt.excluded.total_gpu_hours,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)
    db.commit()
