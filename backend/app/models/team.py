"""Team model for Heliox-AI."""
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import String, Numeric, Boolean
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alert_settings import AlertSettings
    from app.models.job import Job
    from app.models.team_api_key import TeamAPIKey
    from app.models.team_member import TeamMember
    from app.integrations.models import IntegrationConnection
    from app.models.usage import UsageEvent, UsageDailyRollup
    from app.models.billing import TeamSubscription, TeamEntitlement
    from app.models.oauth_identity import OAuthIdentity


class Team(Base, UUIDMixin, TimestampMixin):
    """
    Team model representing a team/organization in Heliox.
    
    A team can have multiple jobs and is used for organizing
    and tracking GPU usage and costs.
    """
    
    __tablename__ = "teams"
    
    # Fields
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique name of the team"
    )
    monthly_budget_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Monthly infra budget in USD"
    )
    
    # SSO Configuration
    allowed_email_domains: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String(255)),
        nullable=True,
        comment="Allowed email domains for SSO (e.g., ['company.com'])"
    )
    sso_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether SSO is enabled for this team"
    )
    sso_enforce_domain: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether to enforce domain allowlist for SSO logins"
    )
    
    # Relationships
    jobs: Mapped[List["Job"]] = relationship(
        "Job",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    alert_settings: Mapped[Optional["AlertSettings"]] = relationship(
        "AlertSettings",
        back_populates="team",
        uselist=False,
        cascade="all, delete-orphan"
    )
    api_keys: Mapped[List["TeamAPIKey"]] = relationship(
        "TeamAPIKey",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    members: Mapped[List["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    integration_connections: Mapped[List["IntegrationConnection"]] = relationship(
        "IntegrationConnection",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    usage_events: Mapped[List["UsageEvent"]] = relationship(
        "UsageEvent",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select"  # Don't eager load usage events
    )
    usage_daily_rollups: Mapped[List["UsageDailyRollup"]] = relationship(
        "UsageDailyRollup",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select"  # Don't eager load rollups
    )
    subscription: Mapped[Optional["TeamSubscription"]] = relationship(
        "TeamSubscription",
        back_populates="team",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    entitlement: Mapped[Optional["TeamEntitlement"]] = relationship(
        "TeamEntitlement",
        back_populates="team",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    oauth_identities: Mapped[List["OAuthIdentity"]] = relationship(
        "OAuthIdentity",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name={self.name})>"

