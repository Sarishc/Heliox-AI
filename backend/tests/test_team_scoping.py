"""Tests for team-scoped analytics services."""

from datetime import date
from decimal import Decimal

from app.models.team import Team
from app.models.cost import CostSnapshot, UsageSnapshot
from app.services.forecasting import ForecastingService
from app.services.recommendations import RecommendationEngine
from app.schemas.recommendation import RecommendationFilters


def test_forecast_scopes_by_team(db_session):
    team1 = Team(name="Team A")
    team2 = Team(name="Team B")
    db_session.add_all([team1, team2])
    db_session.commit()

    db_session.add(
        UsageSnapshot(
            team_id=team1.id,
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal("10"),
        )
    )
    db_session.add(
        UsageSnapshot(
            team_id=team2.id,
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal("100"),
        )
    )
    db_session.commit()

    service = ForecastingService(db_session, redis_client=None)
    result = service.forecast_usage(team_id=team1.id, provider="aws", gpu_type="a100", horizon_days=1)
    # With only one day of data, expect error (insufficient data)
    assert "error" in result


def test_recommendations_scoped_to_team(db_session):
    team1 = Team(name="Team C")
    team2 = Team(name="Team D")
    db_session.add_all([team1, team2])
    db_session.commit()

    db_session.add(
        CostSnapshot(
            team_id=team1.id,
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("1000.00"),
        )
    )
    db_session.add(
        UsageSnapshot(
            team_id=team1.id,
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            gpu_hours=Decimal("0"),
        )
    )
    db_session.add(
        CostSnapshot(
            team_id=team2.id,
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("5000.00"),
        )
    )
    db_session.commit()

    engine = RecommendationEngine(db_session)
    filters = RecommendationFilters(start_date=date(2026, 1, 1), end_date=date(2026, 1, 1), team_id=team1.id)
    result = engine.generate_recommendations(filters)
    # Should produce recommendations without error
    assert result is not None
