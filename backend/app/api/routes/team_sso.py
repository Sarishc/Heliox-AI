"""Team SSO settings API routes."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.models.team_api_key import TeamAPIKey
from app.models.team import Team

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


class UpdateSSOSettingsRequest(BaseModel):
    """Update SSO settings request."""
    sso_enabled: bool = Field(description="Enable or disable SSO")
    sso_enforce_domain: bool = Field(
        default=False,
        description="Enforce domain allowlist"
    )
    allowed_email_domains: Optional[List[str]] = Field(
        default=None,
        description="List of allowed email domains (e.g., ['company.com'])"
    )


@router.get("/settings", response_model=SSOSettingsResponse)
async def get_sso_settings(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key)
):
    """
    Get SSO settings for team.
    
    Returns current SSO configuration.
    """
    team = db.query(Team).filter(Team.id == api_key.team_id).first()
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    # Check if Google OAuth is configured (backend)
    from app.core.config import get_settings
    settings = get_settings()
    google_oauth_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    
    return SSOSettingsResponse(
        team_id=str(team.id),
        sso_enabled=team.sso_enabled,
        sso_enforce_domain=team.sso_enforce_domain,
        allowed_email_domains=team.allowed_email_domains,
        google_oauth_configured=google_oauth_configured
    )


@router.put("/settings", response_model=SSOSettingsResponse)
async def update_sso_settings(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    request_data: UpdateSSOSettingsRequest
):
    """
    Update SSO settings for team.
    
    Allows team admins to:
    - Enable/disable SSO
    - Configure domain allowlist
    - Enforce domain restrictions
    """
    team = db.query(Team).filter(Team.id == api_key.team_id).first()
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    # Validate domains if enforcement is enabled
    if request_data.sso_enforce_domain and not request_data.allowed_email_domains:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must specify allowed_email_domains when enforcing domain restrictions"
        )
    
    # Normalize domains (lowercase)
    if request_data.allowed_email_domains:
        request_data.allowed_email_domains = [
            domain.lower().strip()
            for domain in request_data.allowed_email_domains
        ]
    
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
    
    # Check if Google OAuth is configured
    from app.core.config import get_settings
    settings = get_settings()
    google_oauth_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    
    return SSOSettingsResponse(
        team_id=str(team.id),
        sso_enabled=team.sso_enabled,
        sso_enforce_domain=team.sso_enforce_domain,
        allowed_email_domains=team.allowed_email_domains,
        google_oauth_configured=google_oauth_configured
    )
