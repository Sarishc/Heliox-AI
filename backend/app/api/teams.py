"""Team endpoints."""
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.crud import team as crud_team
from app.models.user import User
from app.schemas.team import Team, TeamCreate, TeamUpdate

router = APIRouter()


@router.get("/", response_model=List[Team])
def list_teams(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Retrieve teams.
    """
    teams = crud_team.get_multi(db, skip=skip, limit=limit)
    return teams


@router.post("/", response_model=Team, status_code=status.HTTP_201_CREATED)
def create_team(
    *,
    db: Session = Depends(get_db),
    team_in: TeamCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create new team.
    """
    team = crud_team.get_by_name(db, name=team_in.name)
    if team:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Team with this name already exists"
        )
    team = crud_team.create(db, obj_in=team_in)
    return team


@router.get("/{team_id}", response_model=Team)
def read_team(
    *,
    db: Session = Depends(get_db),
    team_id: UUID,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get team by ID.
    """
    team = crud_team.get(db, id=team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    return team


@router.put("/{team_id}", response_model=Team)
def update_team(
    *,
    db: Session = Depends(get_db),
    team_id: UUID,
    team_in: TeamUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update a team.
    """
    team = crud_team.get(db, id=team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    team = crud_team.update(db, db_obj=team, obj_in=team_in)
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    *,
    db: Session = Depends(get_db),
    team_id: UUID,
    current_user: User = Depends(get_current_active_user)
) -> None:
    """
    Delete a team.
    """
    team = crud_team.get(db, id=team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    crud_team.delete(db, id=team_id)

