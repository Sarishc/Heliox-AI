"""Daily rollup metrics per team."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TeamDailyRollup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "team_daily_rollups"
    
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=0
    )
    total_gpu_hours: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        default=0
    )
    
    __table_args__ = (
        Index(
            "ix_team_daily_rollups_team_date",
            "team_id",
            "date",
            unique=True
        ),
    )
