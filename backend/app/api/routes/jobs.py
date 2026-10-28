"""Job endpoints.

Tenant isolation: every handler first resolves the caller's team IDs and every
query filters on them in SQL. A job outside those teams is reported as 404,
the same as a job that doesn't exist.
"""

from typing import Any, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.core.tenant import require_team_access
from app.crud import job as crud_job
from app.crud.job import DuplicateJobIdError
from app.models.team_member import TeamMember, TeamRole
from app.models.user import User
from app.schemas.job import Job, JobCreate, JobUpdate, check_chronology

router = APIRouter()

JobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
MUTATING_ROLES = [TeamRole.OWNER, TeamRole.ADMIN]


def _member_team_ids(db: Session, user: User) -> List[UUID]:
    return [m.team_id for m in db.query(TeamMember.team_id).filter(TeamMember.user_id == user.id).all()]


def _get_job_or_404(db: Session, user: User, job_id: UUID):
    job = crud_job.get_for_teams(db, id=job_id, team_ids=_member_team_ids(db, user))
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("/", response_model=dict, summary="List jobs")
def list_jobs(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of records to return (max 100)"),
    team_id: Optional[UUID] = Query(None, description="Filter by team ID"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    provider: Optional[str] = Query(None, max_length=100, description="Filter by provider (case-insensitive)"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List jobs in the caller's teams, newest first.

    Filters (team_id, status, provider) only narrow the caller's own teams;
    ``total`` and ``has_more`` are computed under exactly the same predicate.
    """
    if team_id:
        require_team_access(db, user=current_user, team_id=team_id)
        team_ids = [team_id]
    else:
        team_ids = _member_team_ids(db, current_user)

    jobs, total = crud_job.list_for_teams(
        db, team_ids=team_ids, status=status, provider=provider, skip=skip, limit=limit
    )
    return {
        "jobs": [Job.model_validate(j) for j in jobs],
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + len(jobs) < total,
    }


@router.post("/", response_model=Job, status_code=status.HTTP_201_CREATED, summary="Create a job")
def create_job(
    *, db: Session = Depends(get_db), job_in: JobCreate, current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create a job in one of the caller's teams. ``job_id`` (your scheduler's ID) is
    generated when omitted; a job_id that's already taken returns 409.
    """
    # Same 403 whether the team doesn't exist or the caller isn't a member
    require_team_access(db, user=current_user, team_id=job_in.team_id)
    try:
        return crud_job.create_for_team(db, obj_in=job_in)
    except DuplicateJobIdError:
        # job_id is unique across all teams; don't say who owns it
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job_id is already in use. Choose a different job_id or omit it to generate one.",
        )


@router.get("/{job_id}", response_model=Job, summary="Get a job by ID")
def read_job(
    *, db: Session = Depends(get_db), job_id: UUID, current_user: User = Depends(get_current_active_user)
) -> Any:
    """Get a job in one of the caller's teams."""
    return _get_job_or_404(db, current_user, job_id)


@router.put("/{job_id}", response_model=Job, summary="Update a job")
def update_job(
    *,
    db: Session = Depends(get_db),
    job_id: UUID,
    job_in: JobUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update a job (owner/admin). Typical use: mark a running job completed or
    failed and set end_time. team_id and job_id can't be changed.
    """
    job = _get_job_or_404(db, current_user, job_id)
    require_team_access(db, user=current_user, team_id=job.team_id, allowed_roles=MUTATING_ROLES)
    changes = job_in.model_dump(exclude_unset=True)
    try:
        check_chronology(changes.get("start_time", job.start_time), changes.get("end_time", job.end_time))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return crud_job.update(db, db_obj=job, obj_in=job_in)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a job")
def delete_job(
    *, db: Session = Depends(get_db), job_id: UUID, current_user: User = Depends(get_current_active_user)
) -> None:
    """Delete a job (owner/admin)."""
    job = _get_job_or_404(db, current_user, job_id)
    require_team_access(db, user=current_user, team_id=job.team_id, allowed_roles=MUTATING_ROLES)
    crud_job.delete_by_team(db, id=job.id, team_id=job.team_id)
