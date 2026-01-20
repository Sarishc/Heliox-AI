"""Cost snapshot endpoints."""
from datetime import date as date_type
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.core.tenant import get_effective_team_id
from app.crud import cost_snapshot as crud_cost
from app.models.team_api_key import TeamAPIKey
from app.schemas.cost import CostSnapshot, CostSnapshotCreate

router = APIRouter()


@router.get("/", response_model=List[CostSnapshot])
def list_cost_snapshots(
    db: Session = Depends(get_db),
    start_date: Optional[date_type] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date_type] = Query(None, description="End date (inclusive)"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    skip: int = 0,
    limit: int = 100,
    api_key: TeamAPIKey = Depends(verify_team_api_key)
) -> Any:
    """
    Retrieve cost snapshots with optional date range filter.
    """
    team_id = get_effective_team_id(api_key)
    if start_date and end_date:
        if provider:
            snapshots = crud_cost.get_by_provider(
                db, provider=provider, start_date=start_date, end_date=end_date, team_id=team_id
            )
        else:
            snapshots = crud_cost.get_by_date_range(
                db, start_date=start_date, end_date=end_date, team_id=team_id
            )
    else:
        snapshots = crud_cost.get_multi(db, skip=skip, limit=limit, team_id=team_id)
    return snapshots


@router.post("/", response_model=CostSnapshot, status_code=status.HTTP_201_CREATED)
def create_cost_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_in: CostSnapshotCreate,
    api_key: TeamAPIKey = Depends(verify_team_api_key)
) -> Any:
    """
    Create new cost snapshot.
    """
    team_id = get_effective_team_id(api_key)
    snapshot = crud_cost.create(db, obj_in=snapshot_in.model_copy(update={"team_id": team_id}))
    return snapshot


@router.get("/total", response_model=dict)
def get_total_cost(
    *,
    db: Session = Depends(get_db),
    start_date: date_type = Query(..., description="Start date (inclusive)"),
    end_date: date_type = Query(..., description="End date (inclusive)"),
    api_key: TeamAPIKey = Depends(verify_team_api_key)
) -> Any:
    """
    Get total cost for a date range.
    """
    team_id = get_effective_team_id(api_key)
    total = crud_cost.get_total_cost(
        db, start_date=start_date, end_date=end_date, team_id=team_id
    )
    return {"start_date": start_date, "end_date": end_date, "total_cost_usd": total}


@router.get("/{snapshot_id}", response_model=CostSnapshot)
def read_cost_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_id: UUID,
    api_key: TeamAPIKey = Depends(verify_team_api_key)
) -> Any:
    """
    Get cost snapshot by ID.
    """
    team_id = get_effective_team_id(api_key)
    snapshot = crud_cost.get(db, id=snapshot_id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost snapshot not found"
        )
    if snapshot.team_id != team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost snapshot not found"
        )
    return snapshot


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cost_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_id: UUID,
    api_key: TeamAPIKey = Depends(verify_team_api_key)
) -> None:
    """
    Delete a cost snapshot.
    """
    team_id = get_effective_team_id(api_key)
    snapshot = crud_cost.get(db, id=snapshot_id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost snapshot not found"
        )
    if snapshot.team_id != team_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost snapshot not found"
        )
    crud_cost.delete(db, id=snapshot_id)

