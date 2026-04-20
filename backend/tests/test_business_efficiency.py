"""Tests for business efficiency analytics."""
from datetime import date, timedelta
from decimal import Decimal

from app.models.business_metric import BusinessMetric
from app.models.cost import CostSnapshot
from app.models.team import Team
from app.api.routes.analytics import get_business_efficiency


def test_business_efficiency_metrics(db_session):
    team = Team(name="Biz Team")
    db_session.add(team)
    db_session.commit()
    
    start = date(2026, 1, 1)
    for i in range(5):
        db_session.add(
            BusinessMetric(
                team_id=team.id,
                date=start + timedelta(days=i),
                revenue_usd=Decimal("1000.00"),
                active_users=100,
                requests=1000,
            )
        )
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=start + timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                cost_usd=Decimal("200.00"),
            )
        )
    db_session.commit()
    
    response = get_business_efficiency(
        start=start,
        end=start + timedelta(days=4),
        window_days=3,
        db=db_session,
        team_api_key=type("obj", (), {"team_id": team.id})(),
    )
    assert response.revenue_per_gpu_dollar > 0
    assert response.cost_per_active_user > 0
    assert response.efficiency_trends
    assert response.efficiency_trends[0].requests_per_gpu_dollar >= 0
    assert response.efficiency_trends[0].revenue_per_gpu_dollar_smoothed >= 0
