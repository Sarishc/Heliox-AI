"""Finance runway endpoint."""
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from typing import Union
from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.db import get_db
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.models.team import Team
from app.services.finance_forecast import FinanceForecastService

router = APIRouter()


@router.get(
    "/runway",
    summary="Infra runway forecast",
    description="Predict infra runway based on current burn."
)
def get_runway_forecast(
    budget_usd_monthly: float | None = Query(None, gt=0),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    method: str = Query("ets", pattern="^(ets|arima)$"),
    top_n: int | None = Query(None, gt=0, le=50),
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
) -> Any:
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    team_id = get_effective_team_id(auth_ctx)
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    budget = budget_usd_monthly or (float(team.monthly_budget_usd) if team.monthly_budget_usd else None)
    if budget is None:
        raise HTTPException(
            status_code=400,
            detail="budget_usd_monthly is required or set team.monthly_budget_usd"
        )
    
    service = FinanceForecastService(db)
    result = service.compute_runway(
        team_id=team_id,
        budget_usd_monthly=budget,
        start_date=start_date,
        end_date=end_date,
        method=method,
        top_n=top_n
    )
    record_api_usage(db, team_id=team_id, endpoint="finance_runway")
    return result
