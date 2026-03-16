"""Tests for budget guardrails."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.api.routes.budgets import list_policies
from app.integrations.encryption import get_encryption
from app.models.alert_settings import AlertSettings
from app.models.budget import BudgetPolicy, BudgetEnvironment, BudgetEvent
from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.team import Team
from app.services.budget_guardrails import BudgetGuardrailsService
from app.services.slack_notifications import SlackNotificationService


def _api_key(team_id):
    return type("obj", (), {"team_id": team_id})()


def test_budget_tenant_isolation(db_session):
    team_a = Team(name="Team A")
    team_b = Team(name="Team B")
    db_session.add_all([team_a, team_b])
    db_session.commit()

    policy_a = BudgetPolicy(
        team_id=team_a.id,
        environment=BudgetEnvironment.prod,
        project=None,
        monthly_budget_usd=Decimal("1000.00"),
        alert_thresholds=[0.7],
        is_enabled=True,
    )
    policy_b = BudgetPolicy(
        team_id=team_b.id,
        environment=BudgetEnvironment.prod,
        project=None,
        monthly_budget_usd=Decimal("2000.00"),
        alert_thresholds=[0.7],
        is_enabled=True,
    )
    db_session.add_all([policy_a, policy_b])
    db_session.commit()

    result = list_policies(db=db_session, team_api_key=_api_key(team_a.id))
    assert len(result) == 1
    assert result[0].team_id == team_a.id


def test_budget_threshold_triggers_once_per_month(db_session, monkeypatch):
    team = Team(name="Budget Team")
    db_session.add(team)
    db_session.commit()

    policy = BudgetPolicy(
        team_id=team.id,
        environment=BudgetEnvironment.prod,
        project=None,
        monthly_budget_usd=Decimal("500.00"),
        alert_thresholds=[0.7],
        is_enabled=True,
    )
    db_session.add(policy)
    webhook_url = "https://hooks.slack.com/services/team-a"
    db_session.add(
        AlertSettings(
            team_id=team.id,
            enable_slack=True,
            slack_webhook_encrypted=get_encryption().encrypt_string(webhook_url),
        )
    )
    db_session.commit()

    today = date(2026, 1, 7)
    for i in range(7):
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=today - timedelta(days=i),
                provider="aws",
                gpu_type="a100",
                cost_usd=Decimal("100.00"),
            )
        )
        db_session.add(
            Job(
                job_id=f"job-{i}",
                team_id=team.id,
                model_name="bert",
                provider="aws",
                gpu_type="a100",
                environment="prod",
                start_time=today - timedelta(days=i),
                status="completed",
            )
        )
    db_session.commit()

    sent = []

    async def fake_send(self, blocks, text):
        sent.append(self.webhook_url)
        return True

    monkeypatch.setattr(SlackNotificationService, "_send_slack_message", fake_send)

    service = BudgetGuardrailsService(db_session)
    service.evaluate_policy(policy, as_of=today, send_alerts=True)
    service.evaluate_policy(policy, as_of=today, send_alerts=True)

    events = db_session.query(BudgetEvent).filter(BudgetEvent.budget_policy_id == policy.id).all()
    assert len(events) == 1
    assert sent == ["https://hooks.slack.com/services/team-a"]


def test_budget_predicted_breach_date(db_session):
    team = Team(name="Forecast Budget")
    db_session.add(team)
    db_session.commit()

    policy = BudgetPolicy(
        team_id=team.id,
        environment=BudgetEnvironment.prod,
        project=None,
        monthly_budget_usd=Decimal("1500.00"),
        alert_thresholds=[0.7],
        is_enabled=True,
    )
    db_session.add(policy)
    db_session.commit()

    today = date(2026, 1, 7)
    for i in range(7):
        day = today - timedelta(days=i)
        db_session.add(
            CostSnapshot(
                team_id=team.id,
                date=day,
                provider="aws",
                gpu_type="a100",
                cost_usd=Decimal("100.00"),
            )
        )
        db_session.add(
            Job(
                job_id=f"job-forecast-{i}",
                team_id=team.id,
                model_name="bert",
                provider="aws",
                gpu_type="a100",
                environment="prod",
                start_time=day,
                status="completed",
            )
        )
    db_session.commit()

    service = BudgetGuardrailsService(db_session)
    evaluation = service.evaluate_policy(policy, as_of=today)
    assert evaluation.forecasted_eom_spend > float(policy.monthly_budget_usd)
    assert evaluation.predicted_breach_date is not None
