"""Job endpoints."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.tenant import require_team_access
from app.models.team_member import TeamMember, TeamRole
from app.core.db import get_db
from app.crud import job as crud_job
from app.models.user import User
from app.schemas.job import Job, JobCreate, JobUpdate

router = APIRouter()


@router.get("/", response_model=dict, summary="List jobs")
def list_jobs(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of records to return (max 100)"),
    team_id: Optional[UUID] = Query(None, description="Filter by team ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Retrieve jobs with pagination and optional filters.

    Query Parameters:
    - skip: Number of records to skip (default: 0)
    - limit: Number of records to return (default: 50, max: 100)
    - team_id: Filter by team ID (optional)
    - status: Filter by status (optional)
    - provider: Filter by provider (optional)

    Returns:
    - jobs: List of job records
    - total: Total number of jobs matching filters
    - skip: Number of records skipped
    - limit: Number of records per page
    - has_more: Whether there are more records
    """
    from sqlalchemy import select, func
    from app.models.job import Job as JobModel

    # Build query based on filters
    if team_id:
        require_team_access(db, user=current_user, team_id=team_id)
        jobs = crud_job.get_by_team(db, team_id=team_id, skip=skip, limit=limit)
        # Get count for this filter
        query = select(func.count()).select_from(JobModel).where(JobModel.team_id == team_id)
    elif status:
        jobs = crud_job.get_by_status(db, status=status, skip=skip, limit=limit)
        query = select(func.count()).select_from(JobModel).where(JobModel.status == status)
    elif provider:
        jobs = crud_job.get_by_provider(db, provider=provider, skip=skip, limit=limit)
        query = select(func.count()).select_from(JobModel).where(JobModel.provider == provider)
    else:
        # Restrict to user's teams
        team_ids = [m.team_id for m in db.query(TeamMember).filter(TeamMember.user_id == current_user.id).all()]
        jobs = db.query(JobModel).filter(JobModel.team_id.in_(team_ids)).offset(skip).limit(limit).all()
        query = select(func.count()).select_from(JobModel).where(JobModel.team_id.in_(team_ids))

    # Get total count
    total = db.execute(query).scalar_one()

    return {
        "jobs": jobs,
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
    Create new job.
    """
    # Verify team exists + membership
    from app.crud import team as crud_team

    team = crud_team.get(db, id=job_in.team_id)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    require_team_access(db, user=current_user, team_id=job_in.team_id)
    job = crud_job.create(db, obj_in=job_in)
    return job


@router.get("/{job_id}", response_model=Job, summary="Get a job by ID")
def read_job(
    *, db: Session = Depends(get_db), job_id: UUID, current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get job by ID. Scoped to user's teams at DB level.
    """
    team_ids = [m.team_id for m in db.query(TeamMember).filter(TeamMember.user_id == current_user.id).all()]
    if not team_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    from app.models.job import Job as JobModel

    job = db.query(JobModel).filter(JobModel.id == job_id, JobModel.team_id.in_(team_ids)).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.put("/{job_id}", response_model=Job, summary="Update a job")
def update_job(
    *,
    db: Session = Depends(get_db),
    job_id: UUID,
    job_in: JobUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Update a job. Scoped to user's teams at DB level.
    """
    team_ids = [m.team_id for m in db.query(TeamMember).filter(TeamMember.user_id == current_user.id).all()]
    if not team_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job = None
    for tid in team_ids:
        job = crud_job.get_by_team(db, id=job_id, team_id=tid)
        if job:
            break
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    require_team_access(
        db,
        user=current_user,
        team_id=job.team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    job = crud_job.update(db, db_obj=job, obj_in=job_in)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a job")
def delete_job(
    *, db: Session = Depends(get_db), job_id: UUID, current_user: User = Depends(get_current_active_user)
) -> None:
    """
    Delete a job. Scoped to user's teams at DB level. Requires owner/admin.
    """
    team_ids = [m.team_id for m in db.query(TeamMember).filter(TeamMember.user_id == current_user.id).all()]
    if not team_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job = None
    for tid in team_ids:
        job = crud_job.get_by_team(db, id=job_id, team_id=tid)
        if job:
            break
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    require_team_access(
        db,
        user=current_user,
        team_id=job.team_id,
        allowed_roles=[TeamRole.OWNER, TeamRole.ADMIN],
    )
    crud_job.delete_by_team(db, id=job_id, team_id=job.team_id)
