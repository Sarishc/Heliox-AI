"""Team endpoints."""
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.audit import record_audit_event
from app.core.db import get_db
from app.core.tenant import require_team_access
from app.crud import team as crud_team
from app.crud import team_member as crud_team_member
from app.models.user import User
from app.schemas.team import Team, TeamCreate, TeamUpdate, TeamBudgetUpdate
from app.schemas.team_member import TeamMemberCreate, TeamMemberUpdate, TeamMemberResponse
from app.schemas.audit import AuditLogResponse
from app.models.audit_log import AuditLog
from app.models.team_member import TeamRole
from app.models.team_api_key import TeamAPIKey
from app.schemas.team_api_key import TeamAPIKeyCreate, TeamAPIKeyResponse, TeamAPIKeyCreateResponse

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
    teams = (
        db.query(crud_team.model)
        .join(crud_team_member.model, crud_team_member.model.team_id == crud_team.model.id)
        .filter(crud_team_member.model.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
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
    # Add creator as owner
    membership = crud_team_member.create(
        db,
        obj_in=TeamMemberCreate(
            team_id=team.id,
            user_id=current_user.id,
            role=TeamRole.OWNER
        )
    )
    record_audit_event(
        db,
        team_id=team.id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="team_created",
        metadata={"team_name": team.name}
    )
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
    require_team_access(db, user=current_user, team_id=team_id)
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
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    team = crud_team.get(db, id=team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    team = crud_team.update(db, db_obj=team, obj_in=team_in)
    return team


@router.put("/{team_id}/budget", response_model=Team)
def update_team_budget(
    *,
    db: Session = Depends(get_db),
    team_id: UUID,
    payload: TeamBudgetUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update team monthly budget.
    """
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    team = crud_team.get(db, id=team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    team = crud_team.update(
        db,
        db_obj=team,
        obj_in={"monthly_budget_usd": payload.monthly_budget_usd}
    )
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
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER]
    )
    team = crud_team.get(db, id=team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    crud_team.delete(db, id=team_id)


@router.post("/{team_id}/members", response_model=TeamMemberResponse)
def add_team_member(
    team_id: UUID,
    payload: TeamMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    if payload.team_id != team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_id in path must match payload.team_id"
        )
    existing = crud_team_member.get_by_team_and_user(
        db, team_id=team_id, user_id=payload.user_id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this team"
        )
    membership = crud_team_member.create(db, obj_in=payload)
    record_audit_event(
        db,
        team_id=team_id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="member_added",
        metadata={"member_user_id": str(payload.user_id), "role": payload.role.value}
    )
    return membership


@router.put("/{team_id}/members/{member_id}", response_model=TeamMemberResponse)
def update_team_member(
    team_id: UUID,
    member_id: UUID,
    payload: TeamMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    membership = crud_team_member.get(db, id=member_id)
    if not membership or membership.team_id != team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )
    updated = crud_team_member.update(db, db_obj=membership, obj_in=payload)
    record_audit_event(
        db,
        team_id=team_id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="member_role_changed",
        metadata={"member_id": str(member_id), "role": payload.role.value}
    )
    return updated


@router.get("/{team_id}/audit-logs", response_model=List[AuditLogResponse])
def list_audit_logs(
    team_id: UUID,
    actions: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    query = db.query(AuditLog).filter(AuditLog.team_id == team_id)
    if actions:
        action_list = [a.strip() for a in actions.split(",") if a.strip()]
        query = query.filter(AuditLog.action.in_(action_list))
    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return logs
@router.post("/{team_id}/api-keys", response_model=TeamAPIKeyCreateResponse)
def create_team_api_key(
    team_id: UUID,
    payload: TeamAPIKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create API key for a team (owner/admin only).
    """
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    if payload.team_id != team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="team_id in path must match payload.team_id"
        )
    raw_key = TeamAPIKey.generate_key()
    key_hash = TeamAPIKey.hash_key(raw_key)
    new_key = TeamAPIKey(
        team_id=team_id,
        key_name=payload.key_name,
        key_hash=key_hash,
        is_active=True
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    record_audit_event(
        db,
        team_id=team_id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="api_key_created",
        metadata={"key_name": payload.key_name}
    )
    return TeamAPIKeyCreateResponse(
        id=new_key.id,
        team_id=team_id,
        key_name=new_key.key_name,
        api_key=raw_key,
        is_active=new_key.is_active,
        created_at=new_key.created_at
    )


@router.get("/{team_id}/api-keys", response_model=List[TeamAPIKeyResponse])
def list_team_api_keys(
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    return db.query(TeamAPIKey).filter(TeamAPIKey.team_id == team_id).all()


@router.delete("/{team_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_team_api_key(
    team_id: UUID,
    key_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> None:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    key = db.query(TeamAPIKey).filter(
        TeamAPIKey.id == key_id,
        TeamAPIKey.team_id == team_id
    ).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.is_active = False
    db.commit()
    record_audit_event(
        db,
        team_id=team_id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="api_key_revoked",
        metadata={"key_id": str(key_id)}
    )


@router.post("/{team_id}/api-keys/{key_id}/rotate", response_model=TeamAPIKeyCreateResponse)
def rotate_team_api_key(
    team_id: UUID,
    key_id: UUID,
    payload: TeamAPIKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    require_team_access(
        db,
        user=current_user,
        team_id=team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN]
    )
    key = db.query(TeamAPIKey).filter(
        TeamAPIKey.id == key_id,
        TeamAPIKey.team_id == team_id
    ).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    key.is_active = False
    raw_key = TeamAPIKey.generate_key()
    new_key = TeamAPIKey(
        team_id=team_id,
        key_name=payload.key_name,
        key_hash=TeamAPIKey.hash_key(raw_key),
        is_active=True
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    record_audit_event(
        db,
        team_id=team_id,
        actor_type="user",
        actor_id=str(current_user.id),
        action="api_key_rotated",
        metadata={"old_key_id": str(key_id), "new_key_id": str(new_key.id)}
    )
    return TeamAPIKeyCreateResponse(
        id=new_key.id,
        team_id=team_id,
        key_name=new_key.key_name,
        api_key=raw_key,
        is_active=new_key.is_active,
        created_at=new_key.created_at
    )

