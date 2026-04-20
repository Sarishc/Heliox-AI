"""Cost snapshot endpoints."""
from datetime import date as date_type, timedelta, date
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.db import get_db
from app.core.tenant import get_effective_team_id
from app.crud import cost_snapshot as crud_cost
from app.models.cost import CostSnapshot as CostSnapshotModel
from app.models.team_api_key import TeamAPIKey
from app.schemas.cost import CostSnapshot, CostSnapshotCreate

router = APIRouter()


@router.get("/kpis", summary="Get cost KPI metrics")
def get_cost_kpis(
    db: Session = Depends(get_db),
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session),
) -> Any:
    """Executive KPI summary derived from cost snapshots."""
    team_id = get_effective_team_id(api_key)
    today = date.today()
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_end = month_start - timedelta(days=1)

    mtd = db.query(func.coalesce(func.sum(CostSnapshotModel.cost_usd), 0)).filter(
        CostSnapshotModel.team_id == team_id,
        CostSnapshotModel.date >= month_start,
        CostSnapshotModel.date <= today,
    ).scalar() or 0

    last_month = db.query(func.coalesce(func.sum(CostSnapshotModel.cost_usd), 0)).filter(
        CostSnapshotModel.team_id == team_id,
        CostSnapshotModel.date >= last_month_start,
        CostSnapshotModel.date <= last_month_end,
    ).scalar() or 0

    gpu_count = db.query(func.count(func.distinct(CostSnapshotModel.gpu_type))).filter(
        CostSnapshotModel.team_id == team_id,
        CostSnapshotModel.date >= month_start,
    ).scalar() or 0

    total_all_time = db.query(func.coalesce(func.sum(CostSnapshotModel.cost_usd), 0)).filter(
        CostSnapshotModel.team_id == team_id,
    ).scalar() or 0

    mtd_float = float(mtd)
    last_month_float = float(last_month)
    change = ((mtd_float - last_month_float) / last_month_float * 100) if last_month_float else 0

    if not total_all_time:
        return []

    return [
        {
            "label": "GPU Spend (MTD)",
            "value": mtd_float,
            "format": "currency",
            "change": round(change, 1),
            "changeLabel": "vs last month",
        },
        {
            "label": "Active GPU Types",
            "value": gpu_count,
            "format": "number",
            "change": 0,
            "changeLabel": "this month",
        },
        {
            "label": "Total Spend (All Time)",
            "value": float(total_all_time),
            "format": "currency",
            "change": 0,
            "changeLabel": "all time",
        },
    ]


@router.get("/top-models", summary="Get top models by cost")
def get_top_models(
    db: Session = Depends(get_db),
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session),
) -> Any:
    """Top GPU types by cost (last 30 days)."""
    team_id = get_effective_team_id(api_key)
    since = date.today() - timedelta(days=30)

    rows = (
        db.query(
            CostSnapshotModel.provider,
            CostSnapshotModel.gpu_type,
            func.sum(CostSnapshotModel.cost_usd).label("total_cost"),
            func.count(CostSnapshotModel.id).label("snapshot_count"),
        )
        .filter(CostSnapshotModel.team_id == team_id, CostSnapshotModel.date >= since)
        .group_by(CostSnapshotModel.provider, CostSnapshotModel.gpu_type)
        .order_by(func.sum(CostSnapshotModel.cost_usd).desc())
        .limit(10)
        .all()
    )

    if not rows:
        return []

    max_cost = float(rows[0].total_cost) if rows else 1
    return [
        {
            "id": f"{row.provider}-{row.gpu_type}",
            "model": row.gpu_type,
            "provider": row.provider,
            "instances": row.snapshot_count,
            "hours": row.snapshot_count * 24,
            "cost": float(row.total_cost),
            "utilizationPercent": round(float(row.total_cost) / max_cost * 100, 1),
        }
        for row in rows
    ]


@router.get("/top-teams", summary="Get top teams by cost")
def get_top_teams(
    db: Session = Depends(get_db),
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session),
) -> Any:
    """Top teams by cost — always empty in single-team context."""
    # CostSnapshot is team-scoped; sub-team breakdown requires project/environment grouping
    return []


@router.get("/", response_model=List[CostSnapshot], summary="List cost snapshots")
def list_cost_snapshots(
    db: Session = Depends(get_db),
    start_date: Optional[date_type] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date_type] = Query(None, description="End date (inclusive)"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    skip: int = 0,
    limit: int = 100,
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session)
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


@router.post("/", response_model=CostSnapshot, status_code=status.HTTP_201_CREATED, summary="Create a cost snapshot")
def create_cost_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_in: CostSnapshotCreate,
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session)
) -> Any:
    """
    Create new cost snapshot.
    """
    team_id = get_effective_team_id(api_key)
    snapshot = crud_cost.create(db, obj_in=snapshot_in.model_copy(update={"team_id": team_id}))
    return snapshot


@router.get("/total", response_model=dict, summary="Get total cost aggregated")
def get_total_cost(
    *,
    db: Session = Depends(get_db),
    start_date: date_type = Query(..., description="Start date (inclusive)"),
    end_date: date_type = Query(..., description="End date (inclusive)"),
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session)
) -> Any:
    """
    Get total cost for a date range.
    """
    team_id = get_effective_team_id(api_key)
    total = crud_cost.get_total_cost(
        db, start_date=start_date, end_date=end_date, team_id=team_id
    )
    return {"start_date": start_date, "end_date": end_date, "total_cost_usd": total}


@router.get("/{snapshot_id}", response_model=CostSnapshot, summary="Get a cost snapshot by ID")
def read_cost_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_id: UUID,
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session)
) -> Any:
    """
    Get cost snapshot by ID. Scoped by team at DB level.
    """
    team_id = get_effective_team_id(api_key)
    snapshot = crud_cost.get_by_team(db, id=snapshot_id, team_id=team_id)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost snapshot not found"
        )
    return snapshot


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a cost snapshot")
def delete_cost_snapshot(
    *,
    db: Session = Depends(get_db),
    snapshot_id: UUID,
    api_key: TeamAPIKey | TeamContext = Depends(verify_team_api_key_or_session)
) -> None:
    """
    Delete a cost snapshot. Scoped by team at DB level.
    """
    team_id = get_effective_team_id(api_key)
    if not crud_cost.delete_by_team(db, id=snapshot_id, team_id=team_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cost snapshot not found"
        )

