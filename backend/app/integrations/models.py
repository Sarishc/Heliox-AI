"""Database models for integrations."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import String, DateTime, Text, ForeignKey, JSON, Enum as SQLEnum
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
    provider: Mapped[str] = mapped_column(SQLEnum(IntegrationProvider), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # User-friendly name
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Encrypted configuration (contains API keys, credentials, etc.)
    config_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Status tracking
    status: Mapped[str] = mapped_column(
        SQLEnum(IntegrationStatus),
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

    status: Mapped[str] = mapped_column(SQLEnum(SyncStatus), nullable=False, default=SyncStatus.RUNNING, index=True)

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

    # Relationships
    connection = relationship("IntegrationConnection", back_populates="sync_runs")

    def __repr__(self) -> str:
        return f"<IntegrationSyncRun {self.id} status={self.status.value}>"
