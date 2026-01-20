"""Tests for assistant query routing."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.team import Team
from app.services.assistant import AssistantQueryService


def test_assistant_routes_cost_by_model(db_session):
    team = Team(name="Assistant Team")
    db_session.add(team)
    db_session.commit()
    
    today = date(2026, 1, 10)
    db_session.add(
        Job(
            job_id="assist-job-1",
            team_id=team.id,
            model_name="bert",
            provider="aws",
            gpu_type="a100",
            start_time=today,
            end_time=today,
            status="completed"
        )
    )
    db_session.add(
        CostSnapshot(
            team_id=team.id,
            date=today,
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("100.00")
        )
    )
    db_session.commit()
    
    service = AssistantQueryService(db_session)
    response = service.handle(team_id=team.id, question="Show cost by model for last 7 days")
    assert response["tool_used"] == "analytics_cost_by_model"
    assert response["fallback"] is False
    assert response["tool_trace"]["tool"] == "analytics_cost_by_model"
    assert response["tool_trace"]["duration_ms"] is not None
    assert response["tool_trace"]["row_count"] == 1
    assert response["tool_trace"]["query_count"] >= 1
