"""Alert settings model for team-specific notification configuration."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class AlertSettings(Base):
    """Alert configuration settings for teams."""
    
    __tablename__ = "alert_settings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    team_id = Column(String, ForeignKey("teams.id"), unique=True, nullable=False, index=True)
    
    # Thresholds
    burn_rate_threshold_usd_per_day = Column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("10000.00"),
        comment="Daily spend threshold for burn rate alerts (USD)"
    )
    
    # Notification channels
    enable_slack = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Enable Slack notifications for this team"
    )
    enable_email = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Enable email notifications for this team (future feature)"
    )
    
    # Email configuration (for future use)
    email_recipients = Column(
        String,
        nullable=True,
        comment="Comma-separated list of email addresses"
    )
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    team = relationship("Team", back_populates="alert_settings")

