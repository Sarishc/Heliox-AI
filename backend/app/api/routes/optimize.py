"""Optimization recommendations endpoint."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.services.optimizer import SelfOptimizingAdvisor

router = APIRouter()


@router.get(
    "/recommendations",
    summary="Self-Optimizing Advisor recommendations",
    description="Generate deterministic optimization actions for a team."
)
def get_optimizer_recommendations(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    
    team_id = get_effective_team_id(team_api_key)
    advisor = SelfOptimizingAdvisor(db)
    actions = advisor.generate(team_id=team_id, start_date=start_date, end_date=end_date)
    record_api_usage(db, team_id=team_id, endpoint="optimizer_recommendations")
    return actions


@router.get(
    "/roi",
    summary="Optimization ROI recommendations",
    description="Generate optimization actions with ROI and payback details."
)
def get_optimizer_roi(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    execution_cost_usd: float | None = Query(None, ge=0, description="Override execution cost"),
    baseline_infra_cost_usd: float | None = Query(None, ge=0, description="Baseline infra cost for ROI"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    
    team_id = get_effective_team_id(team_api_key)
    advisor = SelfOptimizingAdvisor(db)
    actions = advisor.generate_with_roi(
        team_id=team_id,
        start_date=start_date,
        end_date=end_date,
        execution_cost_usd=execution_cost_usd,
        baseline_infra_cost_usd=baseline_infra_cost_usd,
    )
    record_api_usage(db, team_id=team_id, endpoint="optimizer_roi")
    return actions
