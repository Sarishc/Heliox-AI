"""Resolve team context from API key or session cookie."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from jose import jwt
from sqlalchemy.orm import Session

from app.auth.cookie_auth import get_token_from_cookie_or_header, is_token_blacklisted
from app.auth.security import SECRET_KEY
from app.core.db import get_db
from app.core.security import _get_team_api_key_by_value, get_request_id
from app.models.team_api_key import TeamAPIKey
from app.models.team_member import TeamMember


@dataclass
class TeamContext:
    """Team context from API key or session - has team_id for get_effective_team_id."""

    team_id: UUID


async def verify_team_api_key_or_session(
    request: Request,
    db: Session = Depends(get_db),
) -> TeamAPIKey | TeamContext:
    """
    Verify team access from X-API-Key header OR from session cookie.
    Returns TeamAPIKey (when from API key) or TeamContext (when from session).
    Both have team_id attribute for get_effective_team_id.
    """
    api_key_value = request.headers.get("X-API-Key")

    # 1. Try API key first
    if api_key_value:
        try:
            api_key = _get_team_api_key_by_value(api_key_value, db, get_request_id())
            request.state.tenant_id = api_key.team_id
            return api_key
        except Exception:
            pass  # Fall through to session

    # 2. Try session cookie
    token = get_token_from_cookie_or_header(request)
    if token and not is_token_blacklisted(token):
        try:
            payload = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=["HS256"],
                options={"require": ["exp", "sub"]},
            )
            email = payload.get("sub")
            if email:
                from app.crud import user as crud_user

                user = crud_user.get_by_email(db, email=email)
                if user:
                    membership = db.query(TeamMember).filter(TeamMember.user_id == user.id).first()
                    if membership:
                        ctx = TeamContext(team_id=membership.team_id)
                        request.state.tenant_id = ctx.team_id
                        return ctx
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing X-API-Key header or valid session. Please login.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def get_team_api_key_or_session_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> TeamAPIKey | TeamContext | None:
    """
    Optional team resolution: X-API-Key or session.
    In dev, returns None when both missing. In prod/staging, raises 401.
    """
    from app.core.config import get_settings

    settings = get_settings()
    api_key_value = request.headers.get("X-API-Key")

    if api_key_value:
        try:
            return _get_team_api_key_by_value(api_key_value, db, get_request_id())
        except Exception:
            pass

    token = get_token_from_cookie_or_header(request)
    if token and not is_token_blacklisted(token):
        try:
            payload = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=["HS256"],
                options={"require": ["exp", "sub"]},
            )
            email = payload.get("sub")
            if email:
                from app.crud import user as crud_user

                user = crud_user.get_by_email(db, email=email)
                if user:
                    membership = db.query(TeamMember).filter(TeamMember.user_id == user.id).first()
                    if membership:
                        return TeamContext(team_id=membership.team_id)
        except Exception:
            pass

    if settings.ENV in ("production", "staging"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header or valid session",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return None
