"""Current user/team info endpoint."""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user_optional
from app.core.db import get_db
from app.core.security import get_team_api_key_if_present
from app.core.tenant import get_effective_team_id
from app.models.team import Team
from app.models.team_api_key import TeamAPIKey
from app.models.user import User
from app.models.team_member import TeamMember
from app.schemas.me import MeResponse
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/me", response_model=MeResponse, summary="Get current team context")
def get_me(
    db: Session = Depends(get_db),
    api_key: TeamAPIKey | None = Depends(get_team_api_key_if_present),
    current_user: User | None = Depends(get_current_user_optional),
) -> Any:
    if api_key:
        team_id = get_effective_team_id(api_key)
        return MeResponse(
            team_id=str(team_id),
            role="api_key",
            feature_flags={"multi_tenant": settings.MULTI_TENANT},
        )
    
    if current_user:
        membership = (
            db.query(TeamMember)
            .filter(TeamMember.user_id == current_user.id)
            .first()
        )
        if membership:
            return MeResponse(
                team_id=str(membership.team_id),
                role=membership.role.value,
                feature_flags={"multi_tenant": settings.MULTI_TENANT},
            )
    
    return MeResponse(
        team_id="",
        role="unknown",
        feature_flags={"multi_tenant": settings.MULTI_TENANT},
    )
