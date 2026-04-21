"""Business KPI metrics for cost correlation."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class BusinessMetric(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "business_metrics"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[str] = mapped_column(Date, nullable=False, index=True)
    revenue_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False)
    requests: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("uq_business_metrics_team_date", "team_id", "date", unique=True),)
