"""Plugin listing endpoint."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import get_current_user_optional
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id, require_team_access
from app.models.team_api_key import TeamAPIKey
from app.models.team_member import TeamRole
from app.plugins.registry import list_plugins
from app.core.db import get_db
from sqlalchemy.orm import Session

router = APIRouter()


@router.get(
    "",
    summary="List loaded plugins",
    description="List loaded integration plugins for team admins."
)
def get_plugins(
    team_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    if current_user:
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user",
            )
        if team_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="team_id is required for user-based access",
            )
        require_team_access(
            db,
            user=current_user,
            team_id=team_id,
            allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
        )
    else:
        effective_team_id = get_effective_team_id(team_api_key)
        if team_id and effective_team_id != team_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="team_id does not match API key",
            )
    return {"plugins": list_plugins()}
