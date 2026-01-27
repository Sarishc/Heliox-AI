"""Saved report, share link, and run models."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ReportRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReportFileType(str, Enum):
    csv = "csv"
    pdf = "pdf"


class SavedReport(Base, UUIDMixin, TimestampMixin):
    """User-saved report configuration."""

    __tablename__ = "saved_reports"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    team = relationship("Team", lazy="selectin")
    created_by = relationship("User", lazy="selectin")

    __table_args__ = (Index("ix_saved_reports_team_created", "team_id", "created_at"),)


class ReportShareLink(Base, UUIDMixin):
    """Public shareable link for a saved report."""

    __tablename__ = "report_share_links"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("saved_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    report = relationship("SavedReport", lazy="selectin")

    __table_args__ = (Index("ix_report_share_links_team_report", "team_id", "report_id"),)


class ReportRun(Base, UUIDMixin, TimestampMixin):
    """Generated report run for CSV/PDF output."""

    __tablename__ = "report_runs"

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("saved_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[ReportRunStatus] = mapped_column(
        SqlEnum(ReportRunStatus, name="report_run_status"),
        nullable=False,
        default=ReportRunStatus.pending,
    )
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_type: Mapped[Optional[ReportFileType]] = mapped_column(
        SqlEnum(ReportFileType, name="report_file_type"),
        nullable=True,
    )

    report = relationship("SavedReport", lazy="selectin")

    __table_args__ = (Index("ix_report_runs_team_report", "team_id", "report_id"),)
