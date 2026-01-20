"""Tests for optimizer ROI calculations."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.cost import CostSnapshot
from app.models.team import Team
from app.models.cost import UsageSnapshot
from app.services.optimizer import SelfOptimizingAdvisor


def test_optimizer_roi_fields(db_session):
    team = Team(name="ROI Team")
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
                cost_usd=Decimal("200.00")
            )
        )
        db_session.add(
            UsageSnapshot(
                team_id=team.id,
                date=start + timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                gpu_hours=4.0
            )
        )
    db_session.commit()
    
    advisor = SelfOptimizingAdvisor(db_session)
    actions = advisor.generate_with_roi(team_id=team.id, start_date=start, end_date=start + timedelta(days=9))
    assert actions, "Expected optimizer actions with ROI"
    action = actions[0]
    assert "execution_cost" in action
    assert "roi" in action
    assert "payback_period_days" in action
    assert "business_priority_score" in action
    assert action["execution_cost"] > 0
    assert action["execution_cost_basis"]
