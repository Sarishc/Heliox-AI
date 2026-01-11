"""Job endpoints."""
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.crud import job as crud_job
from app.models.user import User
from app.schemas.job import Job, JobCreate, JobUpdate

router = APIRouter()


@router.get("/", response_model=dict)
def list_jobs(
    db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of records to return (max 100)"),
    team_id: Optional[UUID] = Query(None, description="Filter by team ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    current_user: User = Depends(get_current_active_user)
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
        jobs = crud_job.get_multi(db, skip=skip, limit=limit)
        query = select(func.count()).select_from(JobModel)
    
    # Get total count
    total = db.execute(query).scalar_one()
    
    return {
        "jobs": jobs,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + len(jobs) < total
    }


@router.post("/", response_model=Job, status_code=status.HTTP_201_CREATED)
def create_job(
    *,
    db: Session = Depends(get_db),
    job_in: JobCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create new job.
    """
    # Verify team exists
    from app.crud import team as crud_team
    team = crud_team.get(db, id=job_in.team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    
    job = crud_job.create(db, obj_in=job_in)
    return job


@router.get("/{job_id}", response_model=Job)
def read_job(
    *,
    db: Session = Depends(get_db),
    job_id: UUID,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get job by ID.
    """
    job = crud_job.get(db, id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    return job


@router.put("/{job_id}", response_model=Job)
def update_job(
    *,
    db: Session = Depends(get_db),
    job_id: UUID,
    job_in: JobUpdate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Update a job.
    """
    job = crud_job.get(db, id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    job = crud_job.update(db, db_obj=job, obj_in=job_in)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    *,
    db: Session = Depends(get_db),
    job_id: UUID,
    current_user: User = Depends(get_current_active_user)
) -> None:
    """
    Delete a job.
    """
    job = crud_job.get(db, id=job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    crud_job.delete(db, id=job_id)

