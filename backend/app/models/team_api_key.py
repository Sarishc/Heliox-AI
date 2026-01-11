"""Team API key model for authentication."""
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class TeamAPIKey(UUIDMixin, TimestampMixin, Base):
    """
    API key model for team authentication.
    
    Each team can have API keys for programmatic access to the API.
    Keys are hashed before storage for security.
    """
    
    __tablename__ = "team_api_keys"
    
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the team that owns this API key"
    )
    
    key_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable name for this API key"
    )
    
    # Hashed API key (using SHA-256 hash for MVP)
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hash of the API key"
    )
    
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether this API key is active"
    )
    
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Timestamp when this key was last used"
    )
    
    # Relationships
    team = relationship("Team", back_populates="api_keys")
    
    def __repr__(self) -> str:
        return f"<TeamAPIKey(id={self.id}, team_id={self.team_id}, name={self.key_name}, active={self.is_active})>"
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new API key (32 bytes, URL-safe base64 encoded)."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_key(key: str) -> str:
        """Hash an API key using SHA-256."""
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()
    
    def verify_key(self, key: str) -> bool:
        """Verify if a provided key matches this API key."""
        if not self.is_active:
            return False
        key_hash = self.hash_key(key)
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(key_hash, self.key_hash)
