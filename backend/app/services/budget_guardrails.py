"""Budget guardrails service."""
from __future__ import annotations

import calendar
import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.budget import BudgetEvent, BudgetPolicy
from app.models.cost import CostSnapshot
from app.models.job import Job
from app.models.cost import UsageSnapshot
from app.models.alert_settings import AlertSettings
from app.services.forecasting import ForecastingService
from app.services.slack_notifications import SlackNotificationService


@dataclass(frozen=True)
class BudgetEvaluation:
    mtd_spend: float
    forecasted_eom_spend: float
    percent_used: float
    predicted_breach_date: Optional[date]


class BudgetGuardrailsService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _month_range(as_of: date) -> tuple[date, date]:
        start = date(as_of.year, as_of.month, 1)
        last_day = calendar.monthrange(as_of.year, as_of.month)[1]
        end = date(as_of.year, as_of.month, last_day)
        return start, end

    def _daily_costs(self, team_id: UUID, start: date, end: date) -> dict[date, float]:
        rows = self.db.execute(
            select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd))
            .where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start,
                CostSnapshot.date <= end,
            )
            .group_by(CostSnapshot.date)
        ).all()
        return {str(row[0]): float(row[1] or 0.0) for row in rows}

    def _daily_usage_shares(
        self,
        team_id: UUID,
        start: date,
        end: date,
        *,
        environment: Optional[str],
        project: Optional[str],
    ) -> tuple[dict[str, float], dict[str, float]]:
        stmt = (
            select(
                UsageSnapshot.date.label("day"),
                func.sum(UsageSnapshot.gpu_hours).label("gpu_hours"),
            )
            .where(
                UsageSnapshot.team_id == team_id,
                UsageSnapshot.date >= start,
                UsageSnapshot.date <= end,
            )
            .group_by("day")
        )

        scoped_stmt = stmt
        if environment:
            scoped_stmt = scoped_stmt.where(UsageSnapshot.environment == environment)
        if project:
            scoped_stmt = scoped_stmt.where(UsageSnapshot.project == project)

        total_rows = self.db.execute(stmt).all()
        scoped_rows = self.db.execute(scoped_stmt).all()

        total_usage = {str(row.day): float(row.gpu_hours or 0.0) for row in total_rows}
        scoped_usage = {str(row.day): float(row.gpu_hours or 0.0) for row in scoped_rows}
        return total_usage, scoped_usage

    def _mtd_spend(self, policy: BudgetPolicy, start: date, end: date) -> float:
        if not policy.environment and not policy.project:
            total = self.db.execute(
                select(func.sum(CostSnapshot.cost_usd)).where(
                    CostSnapshot.team_id == policy.team_id,
                    CostSnapshot.date >= start,
                    CostSnapshot.date <= end,
                )
            ).scalar_one_or_none()
            return float(total or 0.0)

        daily_costs = self._daily_costs(policy.team_id, start, end)
        if not daily_costs:
            return 0.0

        total_usage, scoped_usage = self._daily_usage_shares(
            policy.team_id,
            start,
            end,
            environment=policy.environment.value if policy.environment else None,
            project=policy.project,
        )
        spend = 0.0
        for day, day_cost in daily_costs.items():
            total_amount = total_usage.get(day, 0.0)
            scoped_amount = scoped_usage.get(day, 0.0)
            if total_amount > 0 and scoped_amount > 0:
                spend += day_cost * (scoped_amount / total_amount)
                continue
            spend += self._fallback_job_allocation(
                policy.team_id,
                day,
                day_cost,
                environment=policy.environment.value if policy.environment else None,
                project=policy.project,
            )
        return spend

    def _fallback_job_allocation(
        self,
        team_id: UUID,
        day: str,
        day_cost: float,
        *,
        environment: Optional[str],
        project: Optional[str],
    ) -> float:
        stmt = (
            select(func.count(Job.id))
            .where(
                Job.team_id == team_id,
                Job.start_time.isnot(None),
                func.date(Job.start_time) == day,
            )
        )
        scoped_stmt = stmt
        if environment:
            scoped_stmt = scoped_stmt.where(Job.environment == environment)
        if project:
            scoped_stmt = scoped_stmt.where(Job.project == project)

        total_jobs = self.db.execute(stmt).scalar_one_or_none() or 0
        scoped_jobs = self.db.execute(scoped_stmt).scalar_one_or_none() or 0
        if total_jobs <= 0 or scoped_jobs <= 0:
            return 0.0
        return day_cost * (scoped_jobs / total_jobs)

    def _forecast_remaining_spend(self, team_id: UUID, remaining_days: int) -> list[float]:
        if remaining_days <= 0:
            return []
        forecast_service = ForecastingService(self.db, redis_client=None)
        result = forecast_service.forecast_spend(
            team_id=team_id,
            provider=None,
            gpu_type=None,
            horizon_days=remaining_days,
        )
        if result.get("error"):
            return []
        return [point["value"] for point in result.get("forecast", [])]

    def evaluate_policy(
        self,
        policy: BudgetPolicy,
        *,
        as_of: Optional[date] = None,
        send_alerts: bool = False,
    ) -> BudgetEvaluation:
        as_of = as_of or date.today()
        month_start, month_end = self._month_range(as_of)
        mtd_spend = self._mtd_spend(policy, month_start, as_of)
        remaining_days = (month_end - as_of).days
        forecast_values = self._forecast_remaining_spend(policy.team_id, remaining_days)
        forecasted_eom = mtd_spend + sum(forecast_values)
        budget = float(policy.monthly_budget_usd)
        percent_used = (mtd_spend / budget) if budget > 0 else 0.0

        predicted_breach_date = None
        if budget > 0 and forecast_values:
            cumulative = mtd_spend
            for idx, value in enumerate(forecast_values):
                cumulative += value
                if cumulative >= budget:
                    predicted_breach_date = as_of + timedelta(days=idx + 1)
                    break

        if send_alerts and policy.is_enabled:
            self._emit_threshold_events(
                policy,
                month_start=month_start,
                as_of=as_of,
                percent_used=percent_used,
                mtd_spend=mtd_spend,
                forecasted_eom=forecasted_eom,
                predicted_breach_date=predicted_breach_date,
            )

        return BudgetEvaluation(
            mtd_spend=mtd_spend,
            forecasted_eom_spend=forecasted_eom,
            percent_used=percent_used,
            predicted_breach_date=predicted_breach_date,
        )

    def _emit_threshold_events(
        self,
        policy: BudgetPolicy,
        *,
        month_start: date,
        as_of: date,
        percent_used: float,
        mtd_spend: float,
        forecasted_eom: float,
        predicted_breach_date: Optional[date],
    ) -> None:
        thresholds = sorted(set(policy.alert_thresholds or [0.7, 0.85, 1.0]))
        webhook_url = self._get_team_webhook(policy.team_id)
        email_recipients, email_enabled = self._get_team_email_config(policy.team_id)

        for threshold in thresholds:
            if percent_used < float(threshold):
                continue
            existing = self.db.execute(
                select(BudgetEvent.id).where(
                    BudgetEvent.budget_policy_id == policy.id,
                    BudgetEvent.threshold == Decimal(str(threshold)),
                    BudgetEvent.date >= month_start,
                    BudgetEvent.date <= as_of,
                )
            ).first()
            if existing:
                continue
            delivered_via = "none"
            if webhook_url:
                slack_service = SlackNotificationService(webhook_url=webhook_url)
                slack_delivered = self._send_budget_alert(
                    slack_service,
                    policy=policy,
                    mtd_spend=mtd_spend,
                    forecasted_eom_spend=forecasted_eom,
                    percent_used=percent_used,
                    predicted_breach_date=predicted_breach_date,
                )
                if slack_delivered:
                    delivered_via = "slack"
            if email_enabled and email_recipients:
                email_delivered = self._send_budget_alert_email(
                    to_emails=email_recipients,
                    policy=policy,
                    mtd_spend=mtd_spend,
                    forecasted_eom_spend=forecasted_eom,
                    percent_used=percent_used,
                    predicted_breach_date=predicted_breach_date,
                )
                if email_delivered:
                    delivered_via = f"{delivered_via},email" if delivered_via != "none" else "email"
            event = BudgetEvent(
                team_id=policy.team_id,
                budget_policy_id=policy.id,
                date=as_of,
                threshold=Decimal(str(threshold)),
                spend_usd=Decimal(str(round(mtd_spend, 2))),
                budget_usd=policy.monthly_budget_usd,
                predicted_breach_date=predicted_breach_date,
                delivered_via=delivered_via,
            )
            self.db.add(event)
            self.db.commit()

    def _get_team_webhook(self, team_id: UUID) -> Optional[str]:
        from app.services.webhook_secrets import get_webhook_url

        return get_webhook_url(self.db, team_id)

    def _get_team_email_config(self, team_id: UUID) -> tuple[list, bool]:
        from app.services.slack_notifications import _get_team_email_config as get_email_config

        return get_email_config(self.db, team_id)

    def _send_budget_alert_email(
        self,
        *,
        to_emails: list,
        policy: BudgetPolicy,
        mtd_spend: float,
        forecasted_eom_spend: float,
        percent_used: float,
        predicted_breach_date: Optional[date],
    ) -> bool:
        from app.services.email_notifications import send_budget_alert_email

        async def _send():
            return await send_budget_alert_email(
                to_emails=to_emails,
                env_label=policy.environment.value if policy.environment else "all",
                project_label=policy.project or "all",
                budget=float(policy.monthly_budget_usd),
                mtd_spend=mtd_spend,
                percent_used=percent_used,
                forecasted_eom=forecasted_eom_spend,
                predicted_breach_date=predicted_breach_date,
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return asyncio.run_coroutine_threadsafe(_send(), loop).result()
        return asyncio.run(_send())

    @staticmethod
    def _send_budget_alert(
        slack_service: SlackNotificationService,
        *,
        policy: BudgetPolicy,
        mtd_spend: float,
        forecasted_eom_spend: float,
        percent_used: float,
        predicted_breach_date: Optional[date],
    ) -> bool:
        async def _send():
            return await slack_service.send_budget_alert(
                policy=policy,
                mtd_spend=mtd_spend,
                forecasted_eom_spend=forecasted_eom_spend,
                percent_used=percent_used,
                predicted_breach_date=predicted_breach_date,
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return asyncio.run_coroutine_threadsafe(_send(), loop).result()
        return asyncio.run(_send())

    def list_status(self, team_id: UUID, *, as_of: Optional[date] = None) -> list[tuple[BudgetPolicy, BudgetEvaluation]]:
        policies = (
            self.db.query(BudgetPolicy)
            .filter(BudgetPolicy.team_id == team_id, BudgetPolicy.is_enabled.is_(True))
            .all()
        )
        return [(policy, self.evaluate_policy(policy, as_of=as_of)) for policy in policies]
