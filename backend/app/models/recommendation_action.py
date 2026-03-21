"""Recommendation action model - tracks apply/dismiss for optimization recommendations."""
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class RecommendationAction(Base, UUIDMixin, TimestampMixin):
    """
    Tracks when users apply or dismiss recommendations.

    Uses recommendation_fingerprint to deduplicate across ephemeral recommendation IDs.
    Enables idempotent apply/dismiss and status display on refresh.
    """

    __tablename__ = "recommendation_actions"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recommendation_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Hash of type + key evidence for deduplication",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )  # applied | dismissed
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Recommendation type (idle_gpu, long_running_job, off_hours_usage)",
    )
    estimated_savings_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Savings at time of action",
    )
    recommendation_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Title, description, evidence at time of action",
    )
    applied_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who applied/dismissed (if session auth)",
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gpu_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "uq_recommendation_action_team_fingerprint",
            "team_id",
            "recommendation_fingerprint",
            unique=True,
        ),
        Index("ix_recommendation_actions_status", "status"),
        Index("ix_recommendation_actions_team_status", "team_id", "status"),
    )
