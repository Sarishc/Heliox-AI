"""Usage snapshot endpoints."""
from datetime import date as date_type
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.deps import get_current_active_user
from app.core.db import get_db
from app.crud import usage_snapshot as crud_usage
from app.models.user import User
from app.schemas.cost import UsageSnapshot, UsageSnapshotCreate

router = APIRouter()


@router.get("/", response_model=List[UsageSnapshot])
def list_usage_snapshots(
    db: Session = Depends(get_db),
    start_date: Optional[date_type] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date_type] = Query(None, description="End date (inclusive)"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Retrieve usage snapshots with optional date range filter.
    """
    if start_date and end_date:
        if provider:
            snapshots = crud_usage.get_by_provider(
                db, provider=provider, start_date=start_date, end_date=end_date
            )
        else:
            snapshots = crud_usage.get_by_date_range(
                db, start_date=start_date, end_date=end_date
            )
    else:
        snapshots = crud_usage.get_multi(db, skip=skip, limit=limit)
    return snapshots


@router.post("/", response_model=UsageSnapshot, status_code=status.HTTP_201_CREATED)
def create_usage_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_in: UsageSnapshotCreate,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Create new usage snapshot.
    """
    snapshot = crud_usage.create(db, obj_in=snapshot_in)
    return snapshot


@router.get("/total", response_model=dict)
def get_total_usage(
    *,
    db: Session = Depends(get_db),
    start_date: date_type = Query(..., description="Start date (inclusive)"),
    end_date: date_type = Query(..., description="End date (inclusive)"),
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get total GPU hours for a date range.
    """
    total = crud_usage.get_total_hours(
        db, start_date=start_date, end_date=end_date
    )
    return {"start_date": start_date, "end_date": end_date, "total_gpu_hours": total}


@router.get("/{snapshot_id}", response_model=UsageSnapshot)
def read_usage_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_id: UUID,
    current_user: User = Depends(get_current_active_user)
) -> Any:
    """
    Get usage snapshot by ID.
    """
    snapshot = crud_usage.get(db, id=snapshot_id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usage snapshot not found"
        )
    return snapshot


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_usage_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_id: UUID,
    current_user: User = Depends(get_current_active_user)
) -> None:
    """
    Delete a usage snapshot.
    """
    snapshot = crud_usage.get(db, id=snapshot_id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usage snapshot not found"
        )
    crud_usage.delete(db, id=snapshot_id)

