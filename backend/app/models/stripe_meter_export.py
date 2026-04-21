"""Stripe meter export audit model."""

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class StripeMeterExport(Base, UUIDMixin, TimestampMixin):
    """
    Audit record for Stripe meter event exports.

    Tracks which usage rollups have been sent to Stripe for usage-based billing.
    Enables idempotent retries and audit trail.
    """

    __tablename__ = "stripe_meter_exports"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    export_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stripe_identifier: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Idempotency key sent to Stripe (e.g. heliox_teamid_date_type)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
    )  # pending, succeeded, failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "uq_stripe_meter_export_team_date_type",
            "team_id",
            "export_date",
            "event_type",
            unique=True,
        ),
    )
