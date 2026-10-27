"""Unit tests for the recommendation engine's idle-GPU rule.

Utilization is busy GPU-hours / allocated GPU-hours, both reported by the agent
(see app.services.gpu_cost_attribution). Savings equal the idle-waste metric:
measured spend x idle fraction.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.team import Team
from app.schemas.recommendation import RecommendationFilters, RecommendationSeverity
from app.services.recommendations import RecommendationEngine

START = date(2026, 1, 1)
DAYS = 14
DAILY_COST = Decimal("1000.00")
ALLOCATED_PER_DAY = 24.0  # one GPU powered all day


@pytest.fixture
def team(db_session):
    t = Team(name="Recommendation Team")
    db_session.add(t)
    db_session.commit()
    return t


def _seed(db_session, team, utilization: float, days: int = DAYS) -> None:
    for i in range(days):
        day = START + timedelta(days=i)
        db_session.add(CostSnapshot(team_id=team.id, date=day, provider="aws", gpu_type="a100", cost_usd=DAILY_COST))
        db_session.add(
            UsageSnapshot(
                team_id=team.id,
                date=day,
                provider="aws",
                gpu_type="a100",
                gpu_hours=Decimal(str(ALLOCATED_PER_DAY * utilization)),
                allocated_gpu_hours=Decimal(str(ALLOCATED_PER_DAY)),
            )
        )
    db_session.commit()


def _idle_recs(db_session, team, days: int = DAYS, **filter_kwargs):
    filters = RecommendationFilters(
        start_date=START, end_date=START + timedelta(days=days - 1), team_id=team.id, **filter_kwargs
    )
    result = RecommendationEngine(db_session).generate_recommendations(filters)
    return result, [r for r in result.recommendations if r.type.value == "idle_gpu"]


def test_fully_idle_gpus_are_high_severity(db_session, team):
    _seed(db_session, team, utilization=0.0)

    _, idle = _idle_recs(db_session, team)

    assert len(idle) == 1
    rec = idle[0]
    assert rec.severity == RecommendationSeverity.HIGH
    assert rec.estimated_savings_usd == pytest.approx(float(DAILY_COST) * DAYS)
    assert rec.evidence.waste_percentage == 100.0
    assert rec.evidence.expected_usage_hours == pytest.approx(ALLOCATED_PER_DAY * DAYS)
    assert rec.evidence.actual_usage_hours == 0.0


def test_sixty_percent_idle_is_medium_severity(db_session, team):
    _seed(db_session, team, utilization=0.4)

    _, idle = _idle_recs(db_session, team)

    assert idle[0].severity == RecommendationSeverity.MEDIUM
    assert idle[0].estimated_savings_usd == pytest.approx(float(DAILY_COST) * DAYS * 0.6)


def test_forty_percent_idle_is_low_severity(db_session, team):
    _seed(db_session, team, utilization=0.6)

    _, idle = _idle_recs(db_session, team)

    assert idle[0].severity == RecommendationSeverity.LOW


def test_no_idle_recommendation_when_utilization_is_high(db_session, team):
    _seed(db_session, team, utilization=0.8)

    _, idle = _idle_recs(db_session, team)

    assert idle == []


def test_savings_are_measured_spend_times_idle_fraction(db_session, team):
    # 7 days at $1000, 25% busy: 75% of $7000 is idle
    _seed(db_session, team, utilization=0.25, days=7)

    _, idle = _idle_recs(db_session, team, days=7)

    assert idle[0].estimated_savings_usd == 5250.0


def test_filter_by_min_severity(db_session, team):
    _seed(db_session, team, utilization=0.0)

    result, _ = _idle_recs(db_session, team, min_severity=RecommendationSeverity.HIGH)

    assert result.recommendations
    assert all(r.severity == RecommendationSeverity.HIGH for r in result.recommendations)


def test_deterministic_output(db_session, team):
    _seed(db_session, team, utilization=0.0)

    first, _ = _idle_recs(db_session, team)
    second, _ = _idle_recs(db_session, team)

    assert len(first.recommendations) == len(second.recommendations)
    assert first.total_estimated_savings_usd == second.total_estimated_savings_usd
    assert first.summary == second.summary
