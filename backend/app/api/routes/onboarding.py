"""Onboarding endpoints for self-serve setup."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.crud import team as crud_team
from app.crud import team_member as crud_team_member
from app.models.user import User
from app.models.team_api_key import TeamAPIKey
from app.models.team_member import TeamRole
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.schemas.team import TeamCreate
from app.schemas.team_member import TeamMemberCreate

router = APIRouter()


@router.post(
    "/welcome",
    response_model=OnboardingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create team + first API key"
)
def onboarding_welcome(
    payload: OnboardingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    existing = crud_team.get_by_name(db, name=payload.team_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team with this name already exists"
        )
    
    team = crud_team.create(
        db,
        obj_in=TeamCreate(
            name=payload.team_name,
            monthly_budget_usd=payload.monthly_budget_usd
        )
    )
    crud_team_member.create(
        db,
        obj_in=TeamMemberCreate(
            team_id=team.id,
            user_id=current_user.id,
            role=TeamRole.OWNER
        )
    )
    raw_key = TeamAPIKey.generate_key()
    new_key = TeamAPIKey(
        team_id=team.id,
        key_name=payload.api_key_name,
        key_hash=TeamAPIKey.hash_key(raw_key),
        is_active=True
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    
    record_audit_event(
        db,
        team_id=team.id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="team_onboarded",
        metadata={"team_name": team.name, "key_name": payload.api_key_name}
    )
    
    return OnboardingResponse(
        team_id=str(team.id),
        api_key=raw_key,
        message="Welcome to Heliox! Save this API key now; it will not be shown again."
    )
