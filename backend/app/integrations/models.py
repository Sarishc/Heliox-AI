"""Database models for integrations."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.integrations.base import IntegrationProvider, IntegrationStatus, SyncStatus


class IntegrationConnection(Base):
    """
    Integration connection configuration.

    Stores encrypted credentials and configuration for external service integrations.
    """

    __tablename__ = "integration_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Team association
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)

    # Integration details
    provider: Mapped[str] = mapped_column(
        SQLEnum(IntegrationProvider, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # User-friendly name
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Encrypted configuration (contains API keys, credentials, etc.)
    config_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Status tracking
    status: Mapped[str] = mapped_column(
        SQLEnum(IntegrationStatus, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=IntegrationStatus.PENDING,
        index=True,
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sync tracking
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Auto-sync configuration
    auto_sync_enabled: Mapped[bool] = mapped_column(default=True)
    sync_interval_minutes: Mapped[int] = mapped_column(default=60)  # How often to sync

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    created_by: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Cost ledger (migration 038): connections with ledger history are soft-deleted
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Lets tenant-scoped composite foreign keys reference (team_id, id)
    __table_args__ = (UniqueConstraint("team_id", "id", name="uq_integration_connections_team_id"),)

    # Relationships
    team = relationship("Team", back_populates="integration_connections")
    sync_runs = relationship("IntegrationSyncRun", back_populates="connection", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<IntegrationConnection {self.provider.value} for team {self.team_id}>"


class IntegrationSyncRun(Base):
    """
    Record of an integration sync execution.

    Tracks each sync operation for auditing and debugging.
    """

    __tablename__ = "integration_sync_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Connection reference
    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Execution tracking
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(
        SQLEnum(SyncStatus, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=SyncStatus.RUNNING,
        index=True,
    )

    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Metrics (JSON with sync statistics)
    # Example: {"records_fetched": 100, "records_saved": 95, "records_skipped": 5}
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Metadata
    triggered_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )  # manual, scheduled, webhook

    # Cost ledger runs (migration 038). Legacy runs keep pipeline 'legacy' and a NULL phase.
    phase: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    attempt: Mapped[int] = mapped_column(nullable=False, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=5, server_default=text("5"))
    lease_token: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    dispatch_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    phase_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    billing_exempt: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    pipeline: Mapped[str] = mapped_column(String(8), nullable=False, default="legacy", server_default="legacy")

    __table_args__ = (
        UniqueConstraint("id", "connection_id", name="uq_integration_sync_runs_id_connection"),
        CheckConstraint("pipeline IN ('legacy','ledger')", name="ck_sync_runs_pipeline"),
        CheckConstraint(
            "phase IS NULL OR phase IN\n"
            "    ('queued','leased','fetching','publishing','published','partial','failed','abandoned','dispatch_expired')",
            name="ck_sync_runs_phase",
        ),
        CheckConstraint("(phase IS NULL) = (pipeline = 'legacy')", name="ck_sync_runs_phase_pipeline"),
        CheckConstraint(
            "phase IS NULL OR phase NOT IN ('leased','fetching','publishing') "
            "OR (lease_token IS NOT NULL AND fetch_started_at IS NOT NULL)",
            name="ck_sync_runs_inflight_fields",
        ),
        CheckConstraint(
            "phase IS NULL OR phase <> 'queued' OR dispatch_deadline_at IS NOT NULL",
            name="ck_sync_runs_queued_deadline",
        ),
        # At most one ledger run in flight per connection
        Index(
            "uq_sync_runs_inflight",
            "connection_id",
            unique=True,
            postgresql_where=text("phase IN ('queued','leased','fetching','publishing')"),
            sqlite_where=text("phase IN ('queued','leased','fetching','publishing')"),
        ),
    )

    # Relationships
    connection = relationship("IntegrationConnection", back_populates="sync_runs")

    def __repr__(self) -> str:
        return f"<IntegrationSyncRun {self.id} status={self.status.value}>"
