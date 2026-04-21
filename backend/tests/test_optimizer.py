"""Tests for Self-Optimizing Advisor."""

from datetime import date, timedelta
from decimal import Decimal

from app.models.team import Team
from app.models.cost import CostSnapshot, UsageSnapshot
from app.services.optimizer import SelfOptimizingAdvisor


def test_optimizer_generates_actions_for_idle(db_session):
    team = Team(name="Optimizer Team")
    db_session.add(team)
    db_session.commit()

    start = date(2026, 1, 1)
    for i in range(10):
        current = start + timedelta(days=i)
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=current,
                provider="aws",
                gpu_type="a100",
                cost_usd=Decimal("100.00"),
            )
        )
        db_session.add(
            UsageSnapshot(
                team_id=team.id,
                date=current,
                provider="aws",
                gpu_type="a100",
                gpu_hours=Decimal("12.0"),  # 50% utilization
            )
        )
    db_session.commit()

    advisor = SelfOptimizingAdvisor(db_session)
    actions = advisor.generate(team_id=team.id, start_date=start, end_date=start + timedelta(days=9))
    assert len(actions) >= 1
    assert actions[0]["savings_estimate"] > 0
    assert actions[0]["confidence"] in {"low", "medium", "high"}


def test_optimizer_scopes_by_team(db_session):
    team1 = Team(name="Team A")
    team2 = Team(name="Team B")
    db_session.add_all([team1, team2])
    db_session.commit()

    db_session.add(
        CostSnapshot(
            team_id=team2.id,
            date=date(2026, 1, 1),
            provider="aws",
            gpu_type="a100",
            cost_usd=Decimal("1000.00"),
        )
    )
    db_session.commit()

    advisor = SelfOptimizingAdvisor(db_session)
    actions = advisor.generate(team_id=team1.id, start_date=date(2026, 1, 1), end_date=date(2026, 1, 1))
    assert actions == []
