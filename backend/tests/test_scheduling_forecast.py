"""Tests for scheduling forecast service."""

from datetime import date, timedelta
from decimal import Decimal

from app.models.team import Team
from app.models.cost import UsageSnapshot
from app.services.scheduling_forecast import SchedulingForecastService


def test_scheduling_forecast_shapes(db_session):
    team = Team(name="Sched Team")
    db_session.add(team)
    db_session.commit()

    start = date(2026, 1, 1)
    for i in range(14):
        db_session.add(
            UsageSnapshot(
                team_id=team.id,
                date=start + timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                gpu_hours=Decimal("120.0"),  # 5 GPUs/day
            )
        )
    db_session.commit()

    service = SchedulingForecastService(db_session)
    result = service.forecast(team_id=team.id, horizon_days=7)
    assert "projections" in result
    assert len(result["projections"]) == 7
    first = result["projections"][0]
    assert "required_gpus" in first
    assert "utilization_projection" in first
    assert "congestion_probability" in first


def test_scheduling_forecast_insufficient_data(db_session):
    team = Team(name="Sched Team 2")
    db_session.add(team)
    db_session.commit()

    start = date(2026, 1, 1)
    for i in range(3):
        db_session.add(
            UsageSnapshot(
                team_id=team.id,
                date=start + timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                gpu_hours=Decimal("50.0"),
            )
        )
    db_session.commit()

    service = SchedulingForecastService(db_session)
    result = service.forecast(team_id=team.id, horizon_days=7)
    assert "error" in result
