"""Predictive anomaly detection for spend/utilization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot, UsageSnapshot
from app.models.team import Team


@dataclass(frozen=True)
class AnomalyResult:
    anomalies: List[Dict]
    breach_probability: float
    projected_monthly_spend: float
    budget_usd_monthly: Optional[float]


class AnomalyDetectionService:
    """Detect abnormal spend/utilization and predict budget breach."""

    BASELINE_DAYS = 14
    MIN_POINTS = 7
    BREACH_ALERT_THRESHOLD = 0.7
    SPIKE_STD_MULTIPLIER = 2.0

    def __init__(self, db: Session):
        self.db = db

    def detect(self, *, team_id: UUID) -> AnomalyResult:
        end_date = date.today()
        start_date = end_date - timedelta(days=self.BASELINE_DAYS)

        spend_series = self._daily_series(
            CostSnapshot,
            CostSnapshot.cost_usd,
            CostSnapshot.date,
            team_id,
            start_date,
            end_date,
        )
        usage_series = self._daily_series(
            UsageSnapshot,
            UsageSnapshot.gpu_hours,
            UsageSnapshot.date,
            team_id,
            start_date,
            end_date,
        )

        anomalies: List[Dict] = []
        anomalies.extend(self._detect_spike(spend_series, "spend"))
        anomalies.extend(self._detect_spike(usage_series, "utilization"))

        team = self.db.query(Team).filter(Team.id == team_id).first()
        budget = float(team.monthly_budget_usd) if team and team.monthly_budget_usd else None
        projected_monthly_spend, breach_probability = self._breach_probability(spend_series, budget)

        if budget and breach_probability >= self.BREACH_ALERT_THRESHOLD:
            anomalies.append(
                {
                    "type": "budget_breach_risk",
                    "message": "Projected spend is likely to breach the monthly budget.",
                    "severity": "high",
                    "probability": round(breach_probability, 2),
                }
            )

        return AnomalyResult(
            anomalies=anomalies,
            breach_probability=round(breach_probability, 2),
            projected_monthly_spend=round(projected_monthly_spend, 2),
            budget_usd_monthly=round(budget, 2) if budget is not None else None,
        )

    def should_alert(self, result: AnomalyResult) -> bool:
        return bool(result.anomalies)

    def _daily_series(
        self, model, metric, date_field, team_id: UUID, start_date: date, end_date: date
    ) -> List[tuple[date, float]]:
        stmt = (
            select(date_field, func.sum(metric).label("total"))
            .where(
                model.team_id == team_id,
                date_field >= start_date,
                date_field <= end_date,
            )
            .group_by(date_field)
            .order_by(date_field)
        )
        rows = self.db.execute(stmt).all()
        return [(row[0], float(row[1] or 0.0)) for row in rows]

    def _detect_spike(self, series: List[tuple[date, float]], label: str) -> List[Dict]:
        if len(series) < self.MIN_POINTS:
            return []
        values = [value for _, value in series]
        baseline = values[:-1]
        latest_date, latest_value = series[-1]
        mean = sum(baseline) / len(baseline) if baseline else 0.0
        variance = sum((v - mean) ** 2 for v in baseline) / len(baseline) if baseline else 0.0
        std = variance**0.5
        if std == 0:
            return []
        if latest_value > mean + self.SPIKE_STD_MULTIPLIER * std:
            return [
                {
                    "type": f"{label}_spike",
                    "message": f"{label.capitalize()} spiked above normal range on {latest_date}.",
                    "severity": "medium",
                    "value": round(latest_value, 2),
                    "baseline_mean": round(mean, 2),
                    "baseline_std": round(std, 2),
                }
            ]
        return []

    def _breach_probability(
        self, spend_series: List[tuple[date, float]], budget: Optional[float]
    ) -> tuple[float, float]:
        if not spend_series:
            return 0.0, 0.0
        recent = [value for _, value in spend_series[-7:]]
        avg_daily = sum(recent) / len(recent) if recent else 0.0
        projected_monthly = avg_daily * 30.0
        if not budget or budget <= 0:
            return projected_monthly, 0.0
        ratio = (projected_monthly - budget) / budget
        probability = 1 / (1 + (2.71828 ** (-4 * ratio)))
        return projected_monthly, min(max(probability, 0.0), 1.0)
