"""OAuth identity model for SSO authentication."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class OAuthProvider(str, Enum):
    """Supported OAuth providers."""
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"
    OKTA = "okta"


class OAuthIdentity(Base, UUIDMixin, TimestampMixin):
    """
    OAuth identity model for linking external authentication providers.
    
    Stores the connection between a local user and their OAuth provider identity.
    """
    
    __tablename__ = "oauth_identities"
    
    # Team reference
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the team"
    )
    
    # User reference
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the user"
    )
    
    # OAuth provider details
    provider: Mapped[OAuthProvider] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="OAuth provider (google, github, etc.)"
    )
    
    provider_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User ID from OAuth provider"
    )
    
    # Email and verification
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Email from OAuth provider"
    )
    
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether email is verified by provider"
    )
    
    # Profile data (optional)
    name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Full name from OAuth provider"
    )
    
    picture: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
        comment="Profile picture URL from OAuth provider"
    )
    
    # OAuth tokens — Fernet-encrypted at rest (see auth/oauth_google.py).
    # Text (unbounded) because Fernet output grows ~33 % over plaintext length
    # and Google tokens can exceed 400 chars, which overflows VARCHAR(512).
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted OAuth access token"
    )

    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted OAuth refresh token"
    )
    
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When access token expires"
    )
    
    # Last login tracking
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        index=True,
        comment="Last successful OAuth login"
    )
    
    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="oauth_identities")
    user: Mapped["User"] = relationship("User", back_populates="oauth_identities")
    
    __table_args__ = (
        # Unique constraint: one provider identity per user
        Index("uq_oauth_provider_user", "provider", "provider_user_id", unique=True),
        # Index for lookups
        Index("ix_oauth_identities_team_provider", "team_id", "provider"),
        Index("ix_oauth_identities_user_provider", "user_id", "provider"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<OAuthIdentity(user_id={self.user_id}, provider={self.provider.value}, "
            f"email={self.email})>"
        )
