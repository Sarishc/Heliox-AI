"""API usage tracking model."""
from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ApiUsage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "api_usage"
    __table_args__ = (
        UniqueConstraint("team_id", "date", "endpoint", name="uq_api_usage_team_date_endpoint"),
    )
    
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
