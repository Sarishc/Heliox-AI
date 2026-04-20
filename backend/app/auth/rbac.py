"""
RBAC (Role-Based Access Control) dependencies for Heliox.

Centralizes authorization logic for team-scoped operations.
- API keys: Full access (created by owner/admin, used for automation)
- Session: Role check - OWNER/ADMIN for write operations, any member for read
"""
from typing import Union
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user_optional
from app.auth.team_resolution import TeamContext
from app.core.db import get_db
from app.core.security import _get_team_api_key_by_value, get_request_id
from app.core.tenant import require_team_access
from app.models.team_api_key import TeamAPIKey
from app.models.team_member import TeamRole
from app.models.user import User


def require_team_admin_or_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    x_team_id: str | None = Header(None, alias="X-Team-Id"),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> TeamAPIKey | TeamContext:
    """
    Require team access with admin privileges (OWNER or ADMIN).

    Use for: integrations connect/update/delete, budgets create/update/delete,
    billing checkout/portal, reports create/update/delete, SSO settings update.

    - API key: Full access (keys are created by owner/admin)
    - Session: Requires OWNER or ADMIN role. Use X-Team-Id header for multi-team users.
    """
    # 1. API key: allow (backwards compatible, keys are trusted)
    if x_api_key:
        try:
            api_key = _get_team_api_key_by_value(x_api_key, db, get_request_id())
            request.state.tenant_id = api_key.team_id
            return api_key
        except HTTPException:
            raise
        except Exception:
            pass  # Fall through to session

    # 2. Session: require user + role check
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (X-API-Key or session)",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if x_team_id:
        try:
            team_id = UUID(x_team_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Team-Id format",
            )
    else:
        # Auto-resolve team from user's membership (common case: user belongs to one team)
        from app.models.team_member import TeamMember as TM
        membership = (
            db.query(TM)
            .filter(TM.user_id == current_user.id)
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not a member of any team",
            )
        team_id = membership.team_id

    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    request.state.tenant_id = team_id
    return TeamContext(team_id=team_id)


def get_team_id_from_context(
    ctx: Union[TeamAPIKey, TeamContext],
) -> UUID:
    """Extract team_id from TeamAPIKey or TeamContext."""
    return ctx.team_id
