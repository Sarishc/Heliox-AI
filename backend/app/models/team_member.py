"""Team membership model with roles."""

from enum import Enum
from uuid import UUID

from sqlalchemy import Enum as SqlEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TeamRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"


class TeamMember(UUIDMixin, TimestampMixin, Base):
    """
    Team membership with role-based access.
    """

    __tablename__ = "team_members"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[TeamRole] = mapped_column(
        SqlEnum(
            TeamRole,
            name="team_role",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=TeamRole.VIEWER,
    )

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="memberships")
