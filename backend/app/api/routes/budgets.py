"""Budget policy and guardrail endpoints."""
from datetime import date
from decimal import Decimal
from typing import Any, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.rbac import require_team_admin_or_api_key
from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.db import get_db
from app.core.security import get_team_api_key_optional
from app.core.tenant import get_effective_team_id
from app.models.budget import BudgetPolicy, BudgetEvent
from app.models.team_api_key import TeamAPIKey
from app.schemas.budget import (
    BudgetPolicyCreate,
    BudgetPolicyResponse,
    BudgetPolicyUpdate,
    BudgetStatus,
    BudgetEventResponse,
)
from app.schemas.explainability import Component
from app.services.explainability import explain_metric
from app.services.budget_guardrails import BudgetGuardrailsService

router = APIRouter()


def _normalize_thresholds(values: list[float]) -> list[float]:
    cleaned = []
    for value in values:
        if value <= 0 or value > 1.5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="alert_thresholds values must be between 0 and 1.5",
            )
        cleaned.append(round(float(value), 2))
    return sorted(set(cleaned))


@router.get("", response_model=list[BudgetPolicyResponse])
def list_policies(
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
) -> Any:
    team_id = get_effective_team_id(auth_ctx)
    return (
        db.query(BudgetPolicy)
        .filter(BudgetPolicy.team_id == team_id)
        .order_by(BudgetPolicy.created_at.desc())
        .all()
    )


@router.post("", response_model=BudgetPolicyResponse, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: BudgetPolicyCreate,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
) -> Any:
    team_id = auth_ctx.team_id
    thresholds = _normalize_thresholds(payload.alert_thresholds)
    existing = (
        db.query(BudgetPolicy)
        .filter(
            BudgetPolicy.team_id == team_id,
            BudgetPolicy.environment == payload.environment,
            BudgetPolicy.project == payload.project,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Budget policy already exists for this scope",
        )
    policy = BudgetPolicy(
        team_id=team_id,
        environment=payload.environment,
        project=payload.project.lower().strip() if payload.project else None,
        monthly_budget_usd=payload.monthly_budget_usd,
        alert_thresholds=thresholds,
        is_enabled=payload.is_enabled,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.put("/{policy_id}", response_model=BudgetPolicyResponse)
def update_policy(
    policy_id: UUID,
    payload: BudgetPolicyUpdate,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
) -> Any:
    team_id = auth_ctx.team_id
    policy = (
        db.query(BudgetPolicy)
        .filter(BudgetPolicy.id == policy_id, BudgetPolicy.team_id == team_id)
        .first()
    )
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    if payload.environment is not None:
        policy.environment = payload.environment
    if payload.project is not None:
        policy.project = payload.project.lower().strip()
    if payload.monthly_budget_usd is not None:
        policy.monthly_budget_usd = payload.monthly_budget_usd
    if payload.alert_thresholds is not None:
        policy.alert_thresholds = _normalize_thresholds(payload.alert_thresholds)
    if payload.is_enabled is not None:
        policy.is_enabled = payload.is_enabled

    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def disable_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
) -> None:
    team_id = auth_ctx.team_id
    policy = (
        db.query(BudgetPolicy)
        .filter(BudgetPolicy.id == policy_id, BudgetPolicy.team_id == team_id)
        .first()
    )
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    policy.is_enabled = False
    db.add(policy)
    db.commit()


@router.get("/status", response_model=list[BudgetStatus])
def get_budget_status(
    as_of: Optional[date] = Query(None),
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
) -> Any:
    team_id = get_effective_team_id(auth_ctx)
    service = BudgetGuardrailsService(db)
    month_start, month_end = service._month_range(as_of or date.today())
    results = []
    for policy, evaluation in service.list_status(team_id, as_of=as_of):
        explain = None
        if include_explain:
            explain = explain_metric(
                value=round(evaluation.percent_used, 4),
                unit="ratio",
                window=f"{month_start.isoformat()} to {month_end.isoformat()}",
                formula="mtd_spend / monthly_budget",
                components=[
                    Component(name="mtd_spend", value=round(evaluation.mtd_spend, 2), unit="USD", source="cost_snapshots"),
                    Component(name="monthly_budget", value=float(policy.monthly_budget_usd), unit="USD", source="budget_policy"),
                    Component(name="forecasted_eom_spend", value=round(evaluation.forecasted_eom_spend, 2), unit="USD", source="forecast"),
                ],
                assumptions=["MTD spend is allocated by usage share for environment/project scopes."],
                inputs={
                    "data_points": (as_of or date.today()).day,
                    "window_days": (month_end - month_start).days + 1,
                },
            )
        results.append(
            BudgetStatus(
                policy=policy,
                month_start=month_start,
                month_end=month_end,
                mtd_spend_usd=Decimal(str(round(evaluation.mtd_spend, 2))),
                budget_usd=policy.monthly_budget_usd,
                percent_used=round(evaluation.percent_used, 4),
                forecasted_eom_spend_usd=Decimal(str(round(evaluation.forecasted_eom_spend, 2))),
                predicted_breach_date=evaluation.predicted_breach_date,
                explain=explain,
            )
        )
    return results


@router.get("/events", response_model=list[BudgetEventResponse])
def list_budget_events(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
) -> Any:
    team_id = get_effective_team_id(auth_ctx)
    return (
        db.query(BudgetEvent)
        .filter(BudgetEvent.team_id == team_id)
        .order_by(BudgetEvent.created_at.desc())
        .limit(limit)
        .all()
    )
