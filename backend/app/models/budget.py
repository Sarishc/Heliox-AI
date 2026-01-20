"""Budget policy and budget event models."""
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, JSON, Numeric, String, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class BudgetEnvironment(str, Enum):
    prod = "prod"
    staging = "staging"
    dev = "dev"


class BudgetPolicy(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "budget_policies"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    environment: Mapped[BudgetEnvironment] = mapped_column(
        SqlEnum(BudgetEnvironment, name="budget_environment"),
        nullable=False,
        index=True,
    )
    project: Mapped[Optional[str]] = mapped_column(
        String(120),
        nullable=True,
        index=True,
    )
    monthly_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    alert_thresholds: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class BudgetEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "budget_events"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    budget_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("budget_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    spend_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    budget_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    predicted_breach_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    delivered_via: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
