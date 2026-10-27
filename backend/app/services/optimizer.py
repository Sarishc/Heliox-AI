"""Self-Optimizing Advisor for Heliox-AI."""

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.gpu_cost_attribution import measure_idle_waste

logger = logging.getLogger(__name__)


class SelfOptimizingAdvisor:
    """
    Deterministic, team-scoped optimizer based on historical usage and cost.
    """

    MIN_DAYS = 7

    def __init__(self, db: Session):
        self.db = db

    def generate(
        self,
        *,
        team_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict]:
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        actions: List[Dict] = []
        for group in measure_idle_waste(self.db, team_id, start_date, end_date).groups:
            # Need enough days of agent data; without it utilization is unknown, not 0%
            utilization = group.utilization
            if utilization is None or group.measured_days < self.MIN_DAYS:
                continue

            provider, gpu_type, days_count = group.provider, group.gpu_type, group.measured_days
            savings_estimate = round(group.idle_waste_usd, 2)

            risk_level = self._risk_level(utilization)
            confidence = self._confidence(days_count)

            if utilization < 0.5:
                actions.append(
                    {
                        "action": "Right-size underutilized GPUs",
                        "rationale": (
                            f"{provider.upper()} {gpu_type.upper()} utilization is {utilization:.0%} "
                            f"over {days_count} days. Consider downsizing or consolidating workloads."
                        ),
                        "savings_estimate": savings_estimate,
                        "risk_level": risk_level,
                        "confidence": confidence,
                    }
                )
            elif utilization < 0.7:
                actions.append(
                    {
                        "action": "Reduce idle capacity",
                        "rationale": (
                            f"{provider.upper()} {gpu_type.upper()} utilization is {utilization:.0%}. "
                            "Scheduling or auto-scaling could cut idle spend."
                        ),
                        "savings_estimate": savings_estimate,
                        "risk_level": risk_level,
                        "confidence": confidence,
                    }
                )

        # Rank by savings (deterministic)
        actions.sort(key=lambda x: (-x["savings_estimate"], x["action"]))
        return actions

    def generate_with_roi(
        self,
        *,
        team_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        execution_cost_usd: Optional[float] = None,
        baseline_infra_cost_usd: Optional[float] = None,
    ) -> List[Dict]:
        actions = self.generate(team_id=team_id, start_date=start_date, end_date=end_date)
        enriched: List[Dict] = []
        for action in actions:
            savings = float(action.get("savings_estimate") or 0.0)
            if execution_cost_usd is not None:
                execution_cost = float(execution_cost_usd)
                basis = "explicit_execution_cost"
                assumptions = "Execution cost provided by caller."
            elif baseline_infra_cost_usd is not None:
                execution_cost = max(50.0, float(baseline_infra_cost_usd) * 0.005)
                basis = "baseline_infra_cost"
                assumptions = "Execution cost derived as 0.5% of baseline infra cost."
            else:
                execution_cost = self._execution_cost(
                    savings_estimate=savings,
                    risk_level=action.get("risk_level", "medium"),
                    confidence=action.get("confidence", "medium"),
                )
                basis = "heuristic"
                assumptions = "Execution cost estimated from risk/confidence."
            roi = (savings - execution_cost) / execution_cost if execution_cost > 0 else None
            payback_days = self._payback_period_days(execution_cost=execution_cost, monthly_savings=savings)
            priority = self._business_priority_score(
                savings_estimate=savings,
                risk_level=action.get("risk_level", "medium"),
                confidence=action.get("confidence", "medium"),
            )
            enriched.append(
                {
                    **action,
                    "execution_cost": round(execution_cost, 2),
                    "roi": round(roi, 2) if roi is not None else None,
                    "payback_period_days": payback_days,
                    "business_priority_score": round(priority, 2),
                    "execution_cost_basis": basis,
                    "execution_cost_assumptions": assumptions,
                }
            )
        return enriched

    @staticmethod
    def _risk_level(utilization: float) -> str:
        if utilization < 0.3:
            return "low"
        if utilization < 0.6:
            return "medium"
        return "high"

    @staticmethod
    def _confidence(days_count: int) -> str:
        if days_count >= 21:
            return "high"
        if days_count >= 14:
            return "medium"
        return "low"

    @staticmethod
    def _execution_cost(*, savings_estimate: float, risk_level: str, confidence: str) -> float:
        risk_factor = {"low": 0.08, "medium": 0.15, "high": 0.25}.get(risk_level, 0.15)
        confidence_factor = {"low": 1.2, "medium": 1.0, "high": 0.85}.get(confidence, 1.0)
        base_cost = max(50.0, savings_estimate * risk_factor)
        return base_cost * confidence_factor

    @staticmethod
    def _payback_period_days(*, execution_cost: float, monthly_savings: float) -> Optional[int]:
        if monthly_savings <= 0:
            return None
        daily_savings = monthly_savings / 30.0
        if daily_savings <= 0:
            return None
        return max(1, int(round(execution_cost / daily_savings)))

    @staticmethod
    def _business_priority_score(*, savings_estimate: float, risk_level: str, confidence: str) -> float:
        savings_score = min(1.0, savings_estimate / 10000.0)
        confidence_score = {"low": 0.3, "medium": 0.6, "high": 0.9}.get(confidence, 0.6)
        risk_penalty = {"low": 0.1, "medium": 0.25, "high": 0.45}.get(risk_level, 0.25)
        score = (0.6 * savings_score + 0.4 * confidence_score) - risk_penalty
        return max(0.0, min(1.0, score)) * 100
