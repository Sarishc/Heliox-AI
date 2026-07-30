"""Usage metering models for Heliox-AI."""

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.team import Team


class UsageEventType(str, Enum):
    """Types of usage events tracked."""

    API_REQUEST = "api_request"
    INGESTION = "ingestion"
    SEAT = "seat"
    GPU_NODE = "gpu_node"


class UsageEvent(Base, UUIDMixin, TimestampMixin):
    """
    Raw usage event model for tracking billable usage.

    Stores individual usage events before daily rollup.
    Retention: 30 days (cleaned up by retention job).
    """

    __tablename__ = "usage_events"

    # Team reference (for multi-tenant tracking)
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the team that generated this usage",
    )

    # Event details
    event_type: Mapped[UsageEventType] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of usage event (api_request, ingestion, seat, gpu_node)",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Quantity of usage (e.g., 1 API request, 100 cost line items)",
    )

    # Optional metadata
    event_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional event metadata (endpoint, method, user_id, etc.)",
    )

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="usage_events")

    # Composite indexes for efficient querying
    __table_args__ = (
        Index("ix_usage_events_team_created", "team_id", "created_at"),
        Index("ix_usage_events_team_type_created", "team_id", "event_type", "created_at"),
        Index("ix_usage_events_created_at", "created_at"),  # For retention cleanup
    )

    def __repr__(self) -> str:
        return (
            f"<UsageEvent(team_id={self.team_id}, type={self.event_type}, "
            f"quantity={self.quantity}, created_at={self.created_at})>"
        )


class UsageDailyRollup(Base, UUIDMixin, TimestampMixin):
    """
    Daily aggregated usage rollup model.

    Stores aggregated daily usage per team and event type.
    Retention: 12 months.
    """

    __tablename__ = "usage_daily_rollups"

    # Team reference
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the team",
    )

    # Date (UTC)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True, comment="Date of the rollup (UTC)")

    # Event type
    event_type: Mapped[UsageEventType] = mapped_column(
        String(50), nullable=False, index=True, comment="Type of usage event"
    )

    # Aggregated quantity
    total_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total quantity for this date and event type",
    )

    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="usage_daily_rollups")

    # Composite unique constraint for upsert
    __table_args__ = (
        Index(
            "ix_usage_daily_rollups_team_date_type",
            "team_id",
            "date",
            "event_type",
            unique=True,  # Unique constraint for idempotent rollups
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UsageDailyRollup(team_id={self.team_id}, date={self.date}, "
            f"type={self.event_type}, total={self.total_quantity})>"
        )
