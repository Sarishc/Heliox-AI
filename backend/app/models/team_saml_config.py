"""Team SAML configuration for Okta and other SAML 2.0 IdPs."""
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base


class TeamSamlConfig(Base):
    """
    Team-scoped SAML IdP configuration.
    One config per team. Enables Okta and other SAML 2.0 identity providers.
    """

    __tablename__ = "team_saml_config"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # IdP metadata (from Okta app config)
    idp_entity_id: Mapped[str] = mapped_column(String(512), nullable=False)
    idp_sso_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    idp_x509_cert: Mapped[str] = mapped_column(Text, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    team = relationship("Team", back_populates="saml_config", uselist=False)
