"""Tenant scoping helpers for multi-tenant safety."""

from typing import Optional, Union
from uuid import UUID

from fastapi import HTTPException, status

from app.auth.team_resolution import TeamContext
from app.core.config import get_settings
from app.models.team_api_key import TeamAPIKey
from app.models.team_member import TeamRole, TeamMember
from app.models.user import User
from sqlalchemy.orm import Session


def get_effective_team_id(api_key: Optional[Union[TeamAPIKey, TeamContext]]) -> UUID:
    """
    Resolve the effective team_id for a request.
    Accepts TeamAPIKey or TeamContext (from session) - both have team_id.
    - If MULTI_TENANT is enabled, requires a valid team API key or session.
    - If MULTI_TENANT is disabled, always returns SINGLE_TENANT_TEAM_ID.
    """
    settings = get_settings()
    if settings.MULTI_TENANT:
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header or valid session",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        try:
            return UUID(str(api_key.team_id))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key team binding",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    # Single-tenant mode
    try:
        single_team_id = UUID(settings.SINGLE_TENANT_TEAM_ID)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SINGLE_TENANT_TEAM_ID is not a valid UUID",
        )

    if api_key and api_key.team_id != single_team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key does not match SINGLE_TENANT_TEAM_ID",
        )

    return single_team_id


def resolve_ingest_team_id(requested_team_id: Optional[UUID]) -> UUID:
    """
    Resolve team_id for ingestion paths (admin only).
    """
    settings = get_settings()
    if settings.MULTI_TENANT:
        if not requested_team_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="team_id is required when MULTI_TENANT is true",
            )
        return requested_team_id

    # Single-tenant mode
    try:
        single_team_id = UUID(settings.SINGLE_TENANT_TEAM_ID)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SINGLE_TENANT_TEAM_ID is not a valid UUID",
        )

    if requested_team_id and requested_team_id != single_team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_id must match SINGLE_TENANT_TEAM_ID in single-tenant mode",
        )

    return single_team_id


def require_team_access(
    db: Session, *, user: User, team_id: UUID, allowed_roles: Optional[list[TeamRole]] = None
) -> TeamMember:
    """
    Require that a user is a member of the team with an allowed role.
    """
    membership = db.query(TeamMember).filter(TeamMember.team_id == team_id, TeamMember.user_id == user.id).first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a member of this team",
        )
    if allowed_roles and membership.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for this action",
        )
    return membership
