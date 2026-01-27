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
from app.schemas.explainability import Component
from app.services.explainability import explain_metric

router = APIRouter()


@router.get(
    "/recommendations",
    summary="Self-Optimizing Advisor recommendations",
    description="Generate deterministic optimization actions for a team."
)
def get_optimizer_recommendations(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    team_api_key: TeamAPIKey | None = Depends(get_team_api_key_optional),
) -> Any:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")
    
    team_id = get_effective_team_id(team_api_key)
    advisor = SelfOptimizingAdvisor(db)
    actions = advisor.generate(team_id=team_id, start_date=start_date, end_date=end_date)
    if include_explain:
        window_days = 30
        if start_date and end_date:
            window_days = (end_date - start_date).days + 1
        for action in actions:
            action["explain"] = explain_metric(
                value=float(action.get("savings_estimate") or 0.0),
                unit="USD",
                window=f"{window_days} days",
                formula="total_cost * idle_pct",
                components=[
                    Component(name="savings_estimate", value=float(action.get("savings_estimate") or 0.0), unit="USD", source="optimizer"),
                ],
                assumptions=["Idle percentage derived from usage vs expected hours."],
                inputs={
                    "window_days": window_days,
                    "data_points": window_days,
                },
            )
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
    include_explain: bool = Query(False, description="Include metric explainability payload"),
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
    if include_explain:
        window_days = 30
        if start_date and end_date:
            window_days = (end_date - start_date).days + 1
        for action in actions:
            action["roi_explain"] = explain_metric(
                value=float(action.get("roi") or 0.0),
                unit="ratio",
                window=f"{window_days} days",
                formula="(savings_estimate - execution_cost) / execution_cost",
                components=[
                    Component(name="savings_estimate", value=float(action.get("savings_estimate") or 0.0), unit="USD", source="optimizer"),
                    Component(name="execution_cost", value=float(action.get("execution_cost") or 0.0), unit="USD", source="optimizer"),
                ],
                assumptions=[str(action.get("execution_cost_assumptions") or "Execution cost derived from optimizer heuristics.")],
                inputs={
                    "window_days": window_days,
                    "data_points": window_days,
                },
            )
    record_api_usage(db, team_id=team_id, endpoint="optimizer_roi")
    return actions
