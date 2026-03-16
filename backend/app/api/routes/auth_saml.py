"""SAML 2.0 authentication routes for Okta and other IdPs."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.team import Team
from app.models.team_saml_config import TeamSamlConfig
from app.auth.saml import (
    init_saml_login,
    process_saml_response,
    get_sp_metadata,
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


class SamlLoginRequest(BaseModel):
    """Request to initiate SAML login."""
    team_id: str = Field(description="Team ID for SSO")
    redirect_uri: Optional[str] = Field(default=None, description="Frontend redirect after login")


@router.post("/login")
async def saml_login_start(
    request_data: SamlLoginRequest,
    db: Session = Depends(get_db),
):
    """
    Initiate SAML login flow.
    Returns redirect URL to IdP. Frontend redirects user there.
    """
    try:
        redirect_url, state = init_saml_login(
            db=db,
            team_id=request_data.team_id,
            relay_state=request_data.redirect_uri,
        )
        return {"auth_url": redirect_url, "state": state}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/login")
async def saml_login_start_get(
    team_id: str = Query(..., description="Team ID"),
    db: Session = Depends(get_db),
):
    """
    Initiate SAML login via GET (for IdP-initiated or direct links).
    Redirects to IdP.
    """
    try:
        redirect_url, _ = init_saml_login(db=db, team_id=team_id)
        return RedirectResponse(url=redirect_url, status_code=302)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/acs", response_class=HTMLResponse)
async def saml_acs(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    SAML Assertion Consumer Service.
    Receives POST from IdP with SAMLResponse and RelayState.
    Validates assertion, creates session, redirects to dashboard.
    """
    form = await request.form()
    saml_response = form.get("SAMLResponse")
    relay_state = form.get("RelayState", "")

    if not saml_response:
        logger.warning("SAML ACS called without SAMLResponse")
        return _redirect_to_login_error("missing_response")

    try:
        user, team_id, session_token = process_saml_response(
            db=db,
            saml_response=saml_response,
            relay_state=relay_state,
        )
    except ValueError as e:
        logger.warning(f"SAML ACS validation failed: {e}")
        return _redirect_to_login_error(str(e))

    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    dashboard_url = f"{frontend_url.rstrip('/')}/"

    response = RedirectResponse(url=dashboard_url, status_code=302)
    secure = settings.ENV in ("production", "staging")
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=session_token,
        max_age=settings.AUTH_COOKIE_MAX_AGE,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    return response


def _redirect_to_login_error(message: str) -> HTMLResponse:
    """Redirect to login page with error."""
    frontend_url = settings.FRONTEND_URL or "http://localhost:3000"
    error_url = f"{frontend_url}/login?error=saml_failed&message={message}"
    return HTMLResponse(
        content=f'<html><body>Redirecting... <script>window.location.href="{error_url}";</script></body></html>',
        status_code=200,
    )


@router.get("/metadata")
async def saml_metadata(
    team_id: str = Query(..., description="Team ID"),
    db: Session = Depends(get_db),
):
    """
    Return SP metadata XML for IdP configuration.
    Team admins use this when setting up Okta/IdP.
    """
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    saml_config = (
        db.query(TeamSamlConfig)
        .filter(
            TeamSamlConfig.team_id == team_id,
            TeamSamlConfig.enabled == True,
        )
        .first()
    )
    if not saml_config:
        raise HTTPException(
            status_code=404,
            detail="SAML is not configured for this team",
        )

    metadata_xml = get_sp_metadata(team_id, saml_config)
    return Response(content=metadata_xml, media_type="application/xml")
