"""Team SSO settings API routes."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from typing import Union

from app.auth.rbac import require_team_admin_or_api_key
from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.db import get_db
from app.core.plan_enforcement import require_plan_for_team
from app.core.plans import PlanTier
from app.models.team_api_key import TeamAPIKey
from app.models.team import Team
from app.models.team_saml_config import TeamSamlConfig

router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic schemas
class SSOSettingsResponse(BaseModel):
    """SSO settings response."""

    team_id: str
    sso_enabled: bool
    sso_enforce_domain: bool
    allowed_email_domains: Optional[List[str]]
    google_oauth_configured: bool
    saml_configured: bool = False


class SamlConfigRequest(BaseModel):
    """SAML IdP configuration (owner/admin only)."""

    idp_entity_id: str = Field(..., min_length=1, max_length=512)
    idp_sso_url: str = Field(..., min_length=1, max_length=1024)
    idp_x509_cert: str = Field(..., min_length=1)
    enabled: bool = True
    default_role: str = Field(default="viewer", pattern="^(owner|admin|viewer)$")


class SamlConfigResponse(BaseModel):
    """SAML config response (cert not exposed)."""

    team_id: str
    idp_entity_id: str
    idp_sso_url: str
    enabled: bool
    default_role: str


class UpdateSSOSettingsRequest(BaseModel):
    """Update SSO settings request."""

    sso_enabled: bool = Field(description="Enable or disable SSO")
    sso_enforce_domain: bool = Field(default=False, description="Enforce domain allowlist")
    allowed_email_domains: Optional[List[str]] = Field(
        default=None,
        description="List of allowed email domains (e.g., ['company.com'])",
    )


@router.get("/settings", response_model=SSOSettingsResponse)
async def get_sso_settings(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
):
    """
    Get SSO settings for team.

    Returns current SSO configuration.
    """
    team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()

    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    from app.core.config import get_settings

    settings = get_settings()
    google_oauth_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    saml_config = (
        db.query(TeamSamlConfig).filter(TeamSamlConfig.team_id == team.id, TeamSamlConfig.enabled == True).first()
    )
    return SSOSettingsResponse(
        team_id=str(team.id),
        sso_enabled=team.sso_enabled,
        sso_enforce_domain=team.sso_enforce_domain,
        allowed_email_domains=team.allowed_email_domains,
        google_oauth_configured=google_oauth_configured,
        saml_configured=saml_config is not None,
    )


@router.put("/settings", response_model=SSOSettingsResponse)
async def update_sso_settings(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    request_data: UpdateSSOSettingsRequest,
):
    """
    Update SSO settings for team. Requires Enterprise plan.

    Allows team admins to:
    - Enable/disable SSO
    - Configure domain allowlist
    - Enforce domain restrictions
    """
    require_plan_for_team(db, auth_ctx.team_id, PlanTier.ENTERPRISE)
    team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()

    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    # Validate domains if enforcement is enabled
    if request_data.sso_enforce_domain and not request_data.allowed_email_domains:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify allowed_email_domains when enforcing domain restrictions",
        )

    # Normalize domains (lowercase)
    if request_data.allowed_email_domains:
        request_data.allowed_email_domains = [domain.lower().strip() for domain in request_data.allowed_email_domains]

    # Update team settings
    team.sso_enabled = request_data.sso_enabled
    team.sso_enforce_domain = request_data.sso_enforce_domain
    team.allowed_email_domains = request_data.allowed_email_domains

    db.commit()
    db.refresh(team)

    logger.info(
        f"Updated SSO settings for team {team.id}: "
        f"enabled={request_data.sso_enabled}, "
        f"enforce_domain={request_data.sso_enforce_domain}"
    )

    from app.core.config import get_settings

    settings = get_settings()
    google_oauth_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    saml_config = (
        db.query(TeamSamlConfig).filter(TeamSamlConfig.team_id == team.id, TeamSamlConfig.enabled == True).first()
    )
    return SSOSettingsResponse(
        team_id=str(team.id),
        sso_enabled=team.sso_enabled,
        sso_enforce_domain=team.sso_enforce_domain,
        allowed_email_domains=team.allowed_email_domains,
        google_oauth_configured=google_oauth_configured,
        saml_configured=saml_config is not None,
    )


@router.get("/saml", response_model=SamlConfigResponse)
async def get_saml_config(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
):
    """Get SAML config (owner/admin only). Cert not exposed."""
    team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    saml_config = db.query(TeamSamlConfig).filter(TeamSamlConfig.team_id == team.id).first()
    if not saml_config:
        raise HTTPException(status_code=404, detail="SAML not configured")
    return SamlConfigResponse(
        team_id=str(team.id),
        idp_entity_id=saml_config.idp_entity_id,
        idp_sso_url=saml_config.idp_sso_url,
        enabled=saml_config.enabled,
        default_role=saml_config.default_role,
    )


@router.put(
    "/saml",
    response_model=SamlConfigResponse,
    summary="Configure SAML IdP (Enterprise only)",
)
async def update_saml_config(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    request_data: SamlConfigRequest,
):
    """Create or update SAML config. Requires Enterprise plan."""
    require_plan_for_team(db, auth_ctx.team_id, PlanTier.ENTERPRISE)
    team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Normalize cert (strip whitespace, keep PEM)
    cert = request_data.idp_x509_cert.strip()
    if not cert.startswith("-----BEGIN"):
        raise HTTPException(
            status_code=400,
            detail="Invalid X.509 certificate. Paste the full PEM including BEGIN/END lines.",
        )

    saml_config = db.query(TeamSamlConfig).filter(TeamSamlConfig.team_id == team.id).first()
    if saml_config:
        saml_config.idp_entity_id = request_data.idp_entity_id
        saml_config.idp_sso_url = request_data.idp_sso_url
        saml_config.idp_x509_cert = cert
        saml_config.enabled = request_data.enabled
        saml_config.default_role = request_data.default_role
    else:
        from datetime import datetime
        from uuid import uuid4

        saml_config = TeamSamlConfig(
            id=uuid4(),
            team_id=team.id,
            idp_entity_id=request_data.idp_entity_id,
            idp_sso_url=request_data.idp_sso_url,
            idp_x509_cert=cert,
            enabled=request_data.enabled,
            default_role=request_data.default_role,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(saml_config)

    # Enable SSO on team when SAML is configured
    team.sso_enabled = True
    db.commit()
    db.refresh(saml_config)

    logger.info(f"SAML config updated for team {team.id}, enabled={request_data.enabled}")

    return SamlConfigResponse(
        team_id=str(team.id),
        idp_entity_id=saml_config.idp_entity_id,
        idp_sso_url=saml_config.idp_sso_url,
        enabled=saml_config.enabled,
        default_role=saml_config.default_role,
    )


@router.delete("/saml", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saml_config(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
):
    """Remove SAML config (owner/admin only)."""
    team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    db.query(TeamSamlConfig).filter(TeamSamlConfig.team_id == team.id).delete()
    db.commit()
