"""Job model for Heliox-AI."""
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.team import Team


class Job(Base, UUIDMixin, TimestampMixin):
    """
    Job model representing a GPU job execution.
    
    Tracks individual job runs including model, GPU type, provider,
    timing, and status information.
    """
    
    __tablename__ = "jobs"
    
    # External Job Identifier (for idempotent ingestion)
    job_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment="External job identifier for idempotent upserts"
    )
    
    # Foreign Keys
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the team that owns this job"
    )
    
    # Job Configuration
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Name of the ML model being executed"
    )
    
    gpu_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of GPU used (e.g., A100, H100, V100)"
    )
    
    provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Cloud provider or platform (e.g., AWS, GCP, Azure)"
    )
    
    # Timing
    start_time: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When the job started execution"
    )
    
    end_time: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When the job completed or failed"
    )
    
    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        comment="Current status of the job (pending, running, completed, failed)"
    )
    
    # Relationships
    team: Mapped["Team"] = relationship(
        "Team",
        back_populates="jobs",
        lazy="selectin"
    )
    
    # Indexes for common queries
    __table_args__ = (
        Index("ix_jobs_team_id_status", "team_id", "status"),
        Index("ix_jobs_provider_gpu_type", "provider", "gpu_type"),
        Index("ix_jobs_start_time", "start_time"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<Job(id={self.id}, model={self.model_name}, "
            f"gpu={self.gpu_type}, status={self.status})>"
        )

