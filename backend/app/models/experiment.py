"""Experiment models for optimization experiments."""

from datetime import datetime, date
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.team import Team


class Experiment(Base, UUIDMixin, TimestampMixin):
    """Optimization experiment metadata."""

    __tablename__ = "experiments"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    baseline_policy: Mapped[str] = mapped_column(String(255), nullable=False)
    optimized_policy: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="created")

    team: Mapped["Team"] = relationship("Team", lazy="selectin")
    assignments: Mapped[List["ExperimentAssignment"]] = relationship(
        "ExperimentAssignment",
        back_populates="experiment",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    results: Mapped[Optional["ExperimentResult"]] = relationship(
        "ExperimentResult",
        back_populates="experiment",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (Index("ix_experiments_team_dates", "team_id", "start_date", "end_date"),)


class ExperimentAssignment(Base, UUIDMixin, TimestampMixin):
    """Assignment of a job to baseline or optimized group."""

    __tablename__ = "experiment_assignments"

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    group: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="assignments")
    job: Mapped["Job"] = relationship("Job", lazy="selectin")

    __table_args__ = (
        Index("ix_experiment_assignments_group", "experiment_id", "group"),
        Index("uq_experiment_job", "experiment_id", "job_id", unique=True),
    )


class ExperimentResult(Base, UUIDMixin, TimestampMixin):
    """Stored metrics for an experiment."""

    __tablename__ = "experiment_results"

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="results")
