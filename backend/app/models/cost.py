"""Cost and usage snapshot models for Heliox-AI."""
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class CostSnapshot(Base, UUIDMixin, TimestampMixin):
    """
    Cost snapshot model for tracking daily GPU costs.
    
    Stores daily cost information per provider and GPU type
    for cost analysis and reporting.
    """
    
    __tablename__ = "cost_snapshots"
    
    # Date and Provider Info
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date of the cost snapshot"
    )
    
    provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Cloud provider or platform (e.g., AWS, GCP, Azure)"
    )
    
    gpu_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of GPU (e.g., A100, H100, V100)"
    )
    
    # Cost Data
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Cost in USD for this snapshot"
    )
    
    # Composite index and unique constraint for efficient querying and upserts
    __table_args__ = (
        Index(
            "ix_cost_snapshots_date_provider_gpu",
            "date", "provider", "gpu_type",
            unique=True  # Unique constraint for idempotent upserts
        ),
        Index("ix_cost_snapshots_date", "date"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<CostSnapshot(date={self.date}, provider={self.provider}, "
            f"gpu={self.gpu_type}, cost=${self.cost_usd})>"
        )


class UsageSnapshot(Base, UUIDMixin, TimestampMixin):
    """
    Usage snapshot model for tracking daily GPU usage hours.
    
    Stores daily usage information per provider and GPU type
    for usage analysis and capacity planning.
    """
    
    __tablename__ = "usage_snapshots"
    
    # Date and Provider Info
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date of the usage snapshot"
    )
    
    provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Cloud provider or platform (e.g., AWS, GCP, Azure)"
    )
    
    gpu_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of GPU (e.g., A100, H100, V100)"
    )
    
    # Usage Data
    gpu_hours: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=2),
        nullable=False,
        comment="Number of GPU hours used"
    )
    
    # Composite index for efficient querying
    __table_args__ = (
        Index(
            "ix_usage_snapshots_date_provider_gpu",
            "date", "provider", "gpu_type"
        ),
        Index("ix_usage_snapshots_date", "date"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<UsageSnapshot(date={self.date}, provider={self.provider}, "
            f"gpu={self.gpu_type}, hours={self.gpu_hours})>"
        )

