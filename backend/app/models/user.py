"""User model for authentication."""

from typing import Optional
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING, List

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """
    User model for authentication and authorization.

    Stores user credentials and profile information.
    """

    __tablename__ = "users"

    # Authentication
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="User email address (used for login)",
    )

    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="Bcrypt hashed password")

    # Profile
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="User's full name")

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Whether the user account is active",
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Platform admin can access admin endpoints (replaces global API key)",
    )

    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Whether the user has verified their email address",
    )
    email_verification_token: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        unique=True,
        comment="SHA-256 hex token for email verification (stored hashed)",
    )

    # Password reset
    password_reset_token: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        unique=True,
        comment="SHA-256 hex token for password reset (stored hashed)",
    )
    password_reset_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Expiry timestamp for password reset token",
    )

    if TYPE_CHECKING:
        from app.models.team_member import TeamMember
        from app.models.oauth_identity import OAuthIdentity

    memberships: Mapped[List["TeamMember"]] = relationship(
        "TeamMember",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    oauth_identities: Mapped[List["OAuthIdentity"]] = relationship(
        "OAuthIdentity",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, active={self.is_active})>"
