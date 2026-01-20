"""Tests for cost attribution logic."""
from datetime import datetime, date, timedelta
from decimal import Decimal

from app.api.analytics import get_cost_by_model
from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.team import Team


def test_cost_by_model_runtime_allocation(db_session):
    team = Team(name="Attribution Team")
    db_session.add(team)
    db_session.commit()
    
    day = date(2026, 1, 1)
    db_session.add(
        CostSnapshot(
            team_id=team.id,
            date=day,
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("300.00"),
        )
    )
    db_session.add(
        Job(
            job_id="job-a",
            team_id=team.id,
            model_name="model-a",
            provider="aws",
            gpu_type="a100",
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 1, 1, 2, 0, 0),
            status="completed",
        )
    )
    db_session.add(
        Job(
            job_id="job-b",
            team_id=team.id,
            model_name="model-b",
            provider="aws",
            gpu_type="a100",
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 1, 1, 1, 0, 0),
            status="completed",
        )
    )
    db_session.commit()
    
    response = get_cost_by_model(
        start=day,
        end=day,
        db=db_session,
        team_api_key=type("obj", (), {"team_id": team.id})(),
    )
    costs = {item.model_name: item.total_cost_usd for item in response}
    assert round(costs["model-a"], 2) == 200.0
    assert round(costs["model-b"], 2) == 100.0
