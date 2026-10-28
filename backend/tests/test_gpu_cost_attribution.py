"""
Tests for the shared GPU cost attribution and idle-waste service (plan task 1.3).

Every consumer (analytics routes, reports, recommendations, optimizer, assistant)
must get its numbers from app.services.gpu_cost_attribution so they can't disagree.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.routes.analytics import get_cost_by_model, get_idle_waste, get_savings_summary
from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.job import Job
from app.models.team import Team
from app.schemas.recommendation import RecommendationFilters
from app.services.assistant import AssistantQueryService
from app.services.gpu_cost_attribution import attribute_cost_by_model, measure_idle_waste
from app.services.optimizer import SelfOptimizingAdvisor
from app.services.recommendations import RecommendationEngine
from app.services.reports import ReportService

DAY = date(2026, 1, 1)


@pytest.fixture
def team(db_session):
    t = Team(name="Attribution Team")
    db_session.add(t)
    db_session.commit()
    return t


def _ctx(team):
    return type("Ctx", (), {"team_id": team.id})()


def _cost(db, team, day, provider, gpu_type, usd):
    db.add(CostSnapshot(team_id=team.id, date=day, provider=provider, gpu_type=gpu_type, cost_usd=Decimal(usd)))


def _job(db, team, job_id, model, provider, gpu_type, start, end):
    db.add(
        Job(
            job_id=job_id,
            team_id=team.id,
            model_name=model,
            provider=provider,
            gpu_type=gpu_type,
            start_time=start,
            end_time=end,
            status="completed",
        )
    )


def _usage(db, team, day, provider, gpu_type, busy, allocated):
    db.add(
        UsageSnapshot(
            team_id=team.id,
            date=day,
            provider=provider,
            gpu_type=gpu_type,
            gpu_hours=Decimal(str(busy)),
            allocated_gpu_hours=Decimal(str(allocated)),
        )
    )


def _at(hour, day=DAY):
    return datetime(day.year, day.month, day.day) + timedelta(hours=hour)


# ── Attribution ────────────────────────────────────────────────────────────────


def test_spend_only_goes_to_jobs_on_the_same_gpu_type(db_session, team):
    _cost(db_session, team, DAY, "aws", "h100", "800.00")
    _cost(db_session, team, DAY, "aws", "t4", "40.00")
    _job(db_session, team, "j1", "small-model", "aws", "t4", _at(0), _at(4))
    db_session.commit()

    result = attribute_cost_by_model(db_session, team.id, DAY, DAY)

    costs = {m.model_name: m.cost_usd for m in result.models}
    # The T4 job must not absorb H100 spend; with no H100 jobs, it's unattributed
    assert costs["small-model"] == pytest.approx(40.0)
    assert result.unattributed_usd == pytest.approx(800.0)


def test_models_plus_unattributed_equals_total_spend(db_session, team):
    for i in range(3):
        day = DAY + timedelta(days=i)
        _cost(db_session, team, day, "aws", "a100", "300.00")
        _cost(db_session, team, day, "gcp", "h100", "500.00")
    _job(db_session, team, "j1", "m1", "aws", "a100", _at(1), _at(5))
    _job(db_session, team, "j2", "m2", "aws", "a100", _at(2), _at(3))
    _job(db_session, team, "j3", "m2", "gcp", "h100", _at(0, DAY + timedelta(days=1)), _at(6, DAY + timedelta(days=1)))
    db_session.commit()

    result = attribute_cost_by_model(db_session, team.id, DAY, DAY + timedelta(days=2))

    assert result.total_usd == pytest.approx(2400.0)
    assert sum(m.cost_usd for m in result.models) + result.unattributed_usd == pytest.approx(result.total_usd)


def test_job_spanning_midnight_is_split_across_days(db_session, team):
    next_day = DAY + timedelta(days=1)
    _cost(db_session, team, DAY, "aws", "a100", "100.00")
    _cost(db_session, team, next_day, "aws", "a100", "100.00")
    # 22:00 -> 02:00: 2h on each day; another model runs 2h on day two only
    _job(db_session, team, "j1", "overnight", "aws", "a100", _at(22), _at(2, next_day))
    _job(db_session, team, "j2", "daytime", "aws", "a100", _at(10, next_day), _at(12, next_day))
    db_session.commit()

    result = attribute_cost_by_model(db_session, team.id, DAY, next_day)

    costs = {m.model_name: m.cost_usd for m in result.models}
    # Day 1: overnight gets all $100. Day 2: overnight and daytime split $100 evenly
    assert costs["overnight"] == pytest.approx(150.0)
    assert costs["daytime"] == pytest.approx(50.0)


def test_models_sharing_a_gpu_type_are_not_double_counted(db_session, team):
    _cost(db_session, team, DAY, "aws", "a100", "300.00")
    _job(db_session, team, "j1", "model-a", "aws", "A100", _at(0), _at(2))
    _job(db_session, team, "j2", "model-b", "AWS", "a100", _at(0), _at(1))
    db_session.commit()

    result = attribute_cost_by_model(db_session, team.id, DAY, DAY)

    assert sum(m.cost_usd for m in result.models) == pytest.approx(300.0)


def test_dashboard_and_assistant_agree(db_session, team):
    _cost(db_session, team, DAY, "aws", "a100", "300.00")
    _cost(db_session, team, DAY, "aws", "h100", "500.00")
    _job(db_session, team, "j1", "model-a", "aws", "a100", _at(0), _at(2))
    _job(db_session, team, "j2", "model-b", "aws", "a100", _at(0), _at(1))
    _job(db_session, team, "j3", "model-b", "aws", "h100", _at(0), _at(3))
    db_session.commit()

    dashboard = {
        item.model_name: item.total_cost_usd for item in get_cost_by_model(DAY, DAY, False, db_session, _ctx(team))
    }
    assistant_items, _ = AssistantQueryService(db_session)._cost_by_model(team.id, DAY, DAY)
    assistant = {item["model_name"]: item["total_cost_usd"] for item in assistant_items}

    assert dashboard == assistant == {"model-a": 200.0, "model-b": 600.0}


# ── Idle waste ─────────────────────────────────────────────────────────────────


def test_eight_gpu_fleet_at_half_utilization_is_half_idle(db_session, team):
    _cost(db_session, team, DAY, "aws", "a100", "1000.00")
    # 8 GPUs powered all day = 192 allocated GPU-hours, 96 busy
    _usage(db_session, team, DAY, "aws", "a100", busy=96, allocated=192)
    db_session.commit()

    result = measure_idle_waste(db_session, team.id, DAY, DAY)

    assert result.idle_waste_usd == pytest.approx(500.0)
    assert result.coverage == pytest.approx(1.0)


def test_spend_without_agent_data_is_unmeasured_not_idle(db_session, team):
    _cost(db_session, team, DAY, "aws", "a100", "1000.00")
    db_session.commit()

    result = measure_idle_waste(db_session, team.id, DAY, DAY)

    assert result.idle_waste_usd == 0.0
    assert result.unmeasured_cost_usd == pytest.approx(1000.0)
    assert result.coverage == 0.0


def test_partial_coverage_only_counts_measured_groups(db_session, team):
    _cost(db_session, team, DAY, "aws", "a100", "1000.00")
    _cost(db_session, team, DAY, "gcp", "h100", "3000.00")
    _usage(db_session, team, DAY, "aws", "a100", busy=6, allocated=24)  # 75% idle
    db_session.commit()

    result = measure_idle_waste(db_session, team.id, DAY, DAY)

    assert result.idle_waste_usd == pytest.approx(750.0)
    assert result.measured_cost_usd == pytest.approx(1000.0)
    assert result.unmeasured_cost_usd == pytest.approx(3000.0)
    assert result.coverage == pytest.approx(0.25)


def test_busy_hours_above_allocated_are_capped(db_session, team):
    _cost(db_session, team, DAY, "aws", "a100", "100.00")
    _usage(db_session, team, DAY, "aws", "a100", busy=30, allocated=24)
    db_session.commit()

    assert measure_idle_waste(db_session, team.id, DAY, DAY).idle_waste_usd == 0.0


# ── Every consumer uses the same numbers ───────────────────────────────────────


@pytest.fixture
def half_idle_fortnight(db_session, team):
    """14 days, 4 A100s allocated all day, 25% busy, $400/day."""
    for i in range(14):
        day = DAY + timedelta(days=i)
        _cost(db_session, team, day, "aws", "a100", "400.00")
        _usage(db_session, team, day, "aws", "a100", busy=24, allocated=96)
    db_session.commit()
    return DAY, DAY + timedelta(days=13)


def test_idle_waste_route_savings_route_and_report_agree(db_session, team, half_idle_fortnight):
    start, end = half_idle_fortnight
    expected = 14 * 400 * 0.75

    assert get_idle_waste(start, end, db_session, _ctx(team)).value == pytest.approx(expected)
    assert get_savings_summary(start, end, False, db_session, _ctx(team)).estimated_idle_waste_usd == pytest.approx(
        expected
    )
    assert ReportService(db_session)._get_idle_waste(team.id, start, end) == pytest.approx(expected)


def test_idle_recommendation_matches_idle_waste(db_session, team, half_idle_fortnight):
    start, end = half_idle_fortnight

    result = RecommendationEngine(db_session).generate_recommendations(
        RecommendationFilters(start_date=start, end_date=end, team_id=team.id)
    )
    idle = [r for r in result.recommendations if r.type.value == "idle_gpu"]

    assert len(idle) == 1
    assert idle[0].estimated_savings_usd == pytest.approx(14 * 400 * 0.75)
    assert idle[0].evidence.expected_usage_hours == pytest.approx(14 * 96)
    assert idle[0].evidence.actual_usage_hours == pytest.approx(14 * 24)


def test_no_idle_recommendation_or_optimizer_action_without_agent_data(db_session, team):
    for i in range(14):
        _cost(db_session, team, DAY + timedelta(days=i), "aws", "a100", "400.00")
    db_session.commit()
    end = DAY + timedelta(days=13)

    recs = RecommendationEngine(db_session).generate_recommendations(
        RecommendationFilters(start_date=DAY, end_date=end, team_id=team.id)
    )
    actions = SelfOptimizingAdvisor(db_session).generate(team_id=team.id, start_date=DAY, end_date=end)

    # Billing data alone says nothing about utilization; don't call it 100% idle
    assert [r for r in recs.recommendations if r.type.value == "idle_gpu"] == []
    assert actions == []
