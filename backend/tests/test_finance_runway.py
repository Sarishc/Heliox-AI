"""Tests for finance runway forecasting."""

from datetime import date, timedelta
from decimal import Decimal

from app.models.team import Team
from app.models.cost import CostSnapshot
from app.models.job import Job
from app.services.finance_forecast import FinanceForecastService


def test_runway_calculation(db_session):
    team = Team(name="Finance Team")
    db_session.add(team)
    db_session.commit()

    start = date(2026, 1, 1)
    for i in range(10):
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=start + timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                cost_usd=Decimal("100.00"),
            )
        )
        db_session.add(
            Job(
                job_id=f"job-{i}",
                team_id=team.id,
                model_name="bert" if i % 2 == 0 else "llama",
                provider="aws",
                gpu_type="a100",
                job_type="training" if i % 2 == 0 else "inference",
                environment="prod" if i % 2 == 0 else "staging",
                start_time=start + timedelta(days=i),
                status="completed",
            )
        )
    db_session.commit()

    service = FinanceForecastService(db_session)
    result = service.compute_runway(team_id=team.id, budget_usd_monthly=3000.0, method="ets", top_n=1)
    assert result["monthly_burn"] > 0
    assert result["runway_days"] is not None
    assert result["budget_risk_score"] >= 0
    assert result["breakdown"]
    assert len(result["breakdown"]) == 1


def test_runway_no_cost_data(db_session):
    team = Team(name="Finance Team 2")
    db_session.add(team)
    db_session.commit()

    service = FinanceForecastService(db_session)
    result = service.compute_runway(team_id=team.id, budget_usd_monthly=1000.0)
    assert result["monthly_burn"] == 0.0
    assert result["runway_days"] is None
