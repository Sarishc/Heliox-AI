"""OAuth authentication API routes."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token
from app.models.team import Team
from app.auth.oauth_google import (
    build_google_auth_url,
    validate_and_pop_state,
    exchange_code_for_token,
    get_google_userinfo,
    check_domain_allowed,
    get_or_create_user_from_oauth,
    upsert_oauth_identity
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


# Pydantic schemas
class OAuthStartRequest(BaseModel):
    """Request to start OAuth flow."""
    team_id: str = Field(description="Team ID for SSO")
    redirect_uri: Optional[str] = Field(
        default=None,
        description="Frontend redirect URI after OAuth (default: frontend URL)"
    )


class OAuthCallbackResponse(BaseModel):
    """OAuth callback response with token."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    team_id: str
    email: str


@router.post("/google/start")
async def google_oauth_start(
    *,
    db: Session = Depends(get_db),
    request_data: OAuthStartRequest
):
    """
    Start Google OAuth flow.
    
    Flow:
    1. Validate team exists and SSO is enabled
    2. Generate state and nonce
    3. Build Google OAuth URL
    4. Return redirect URL
    """
    # Validate team
    team = db.query(Team).filter(Team.id == request_data.team_id).first()
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    if not team.sso_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SSO is not enabled for this team"
        )
    
    # Build OAuth URL
    frontend_redirect = request_data.redirect_uri or settings.FRONTEND_URL or "http://localhost:3000"
    backend_redirect = settings.GOOGLE_REDIRECT_URI
    
    # Store frontend redirect in state for later
    auth_url, state = build_google_auth_url(
        team_id=str(team.id),
        redirect_uri=backend_redirect
    )
    
    logger.info(f"Started Google OAuth flow for team {team.id}")
    
    return {
        "auth_url": auth_url,
        "state": state
    }


@router.get("/google/callback")
async def google_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="OAuth state token"),
    db: Session = Depends(get_db)
):
    """
    Handle Google OAuth callback.
    
    Flow:
    1. Validate state
    2. Exchange code for token
    3. Get user info from Google
    4. Check domain allowlist
    5. Create/update user and OAuth identity
    6. Issue JWT token
    7. Redirect to frontend with token
    """
    # Validate state
    state_data = validate_and_pop_state(state)
    
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state"
        )
    
    team_id = state_data["team_id"]
    redirect_uri = settings.GOOGLE_REDIRECT_URI
    frontend_redirect = state_data.get("redirect_uri", "http://localhost:3000")
    
    # Get team
    team = db.query(Team).filter(Team.id == team_id).first()
    
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    try:
        # Exchange code for token
        token_response = await exchange_code_for_token(code, redirect_uri)
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in")
        
        if not access_token:
            raise Exception("No access token in response")
        
        # Get user info
        userinfo = await get_google_userinfo(access_token)
        
        email = userinfo.get("email")
        provider_user_id = userinfo.get("id")
        name = userinfo.get("name")
        picture = userinfo.get("picture")
        email_verified = userinfo.get("verified_email", False)
        
        if not email or not provider_user_id:
            raise Exception("Missing required user info from Google")
        
        # Check domain allowlist
        if not check_domain_allowed(email, team):
            logger.warning(
                f"OAuth login blocked for {email} - domain not allowed for team {team.id}"
            )
            # Redirect to frontend with error
            error_url = f"{frontend_redirect}/login?error=domain_not_allowed"
            return RedirectResponse(url=error_url)
        
        # Get or create user
        user = get_or_create_user_from_oauth(
            db=db,
            team_id=team_id,
            email=email,
            name=name,
            email_verified=email_verified
        )
        
        # Upsert OAuth identity
        upsert_oauth_identity(
            db=db,
            team_id=team_id,
            user=user,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=email_verified,
            name=name,
            picture=picture,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in
        )
        
        # Create JWT token for Heliox
        jwt_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "team_id": str(team.id)
            }
        )
        
        logger.info(f"Google OAuth successful for user {user.id}, team {team.id}")
        
        # Redirect to frontend with token
        success_url = f"{frontend_redirect}/auth/callback?token={jwt_token}&team_id={team.id}"
        return RedirectResponse(url=success_url)
    
    except Exception as e:
        logger.error(f"Google OAuth callback failed: {e}", exc_info=True)
        error_url = f"{frontend_redirect}/login?error=oauth_failed&message={str(e)}"
        return RedirectResponse(url=error_url)


@router.get("/google/test")
async def test_google_oauth_config():
    """
    Test Google OAuth configuration.
    
    Returns configuration status (without exposing secrets).
    """
    config_status = {
        "client_id_configured": bool(settings.GOOGLE_CLIENT_ID),
        "client_secret_configured": bool(settings.GOOGLE_CLIENT_SECRET),
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "frontend_url": settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else None
    }
    
    return config_status
