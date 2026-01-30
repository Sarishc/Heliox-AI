"""Team model for Heliox-AI."""
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.alert_settings import AlertSettings
    from app.models.job import Job
    from app.models.team_api_key import TeamAPIKey
    from app.models.team_member import TeamMember
    from app.integrations.models import IntegrationConnection


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
    
    def __repr__(self) -> str:
        return f"<Team(id={self.id}, name={self.name})>"

