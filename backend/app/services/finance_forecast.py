"""Business-aware cost forecasting and runway analysis."""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot
from app.models.job import Job

logger = logging.getLogger(__name__)


class FinanceForecastService:
    """
    Forecast spend and compute runway risk.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def compute_runway(
        self,
        *,
        team_id: UUID,
        budget_usd_monthly: float,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        method: str = "ets",
        top_n: Optional[int] = None
    ) -> Dict:
        if end_date is None:
            latest = self.db.execute(
                select(func.max(CostSnapshot.date)).where(CostSnapshot.team_id == team_id)
            ).scalar_one_or_none()
            end_date = latest or date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=30)
        
        # Daily spend history
        spend_rows = self._fetch_daily_costs(team_id, start_date, end_date)
        daily_costs = [float(row[1]) for row in spend_rows if row[1]]
        if not daily_costs:
            return {
                "monthly_burn": 0.0,
                "runway_days": None,
                "budget_risk_score": 0.0,
                "forecast_method": method,
                "budget_usd_monthly": round(budget_usd_monthly, 2),
                "breakdown": [],
            }
        
        forecast_daily = self._forecast_daily_costs(daily_costs, method=method, horizon_days=30)
        forecast_avg = float(np.mean(forecast_daily)) if forecast_daily else float(np.mean(daily_costs))
        monthly_burn = round(sum(forecast_daily) if forecast_daily else forecast_avg * 30.0, 2)
        runway_days = int(budget_usd_monthly / forecast_avg) if forecast_avg > 0 else None
        
        breakdown, total_cost = self._cost_breakdown(team_id, start_date, end_date)
        correlation_score = self._correlation_risk_from_breakdown(breakdown, total_cost)
        budget_ratio = monthly_burn / budget_usd_monthly if budget_usd_monthly > 0 else 0.0
        budget_risk_score = min(1.0, 0.7 * budget_ratio + 0.3 * correlation_score)
        if top_n is not None:
            breakdown = breakdown[:top_n]
        
        return {
            "monthly_burn": round(monthly_burn, 2),
            "runway_days": runway_days,
            "budget_risk_score": round(budget_risk_score, 2),
            "forecast_method": method,
            "budget_usd_monthly": round(budget_usd_monthly, 2),
            "breakdown": breakdown,
        }
    
    def _fetch_daily_costs(
        self,
        team_id: UUID,
        start_date: date,
        end_date: date
    ) -> List[Tuple[date, float]]:
        return self.db.execute(
            select(CostSnapshot.date, func.sum(CostSnapshot.cost_usd).label("total_cost"))
            .where(
                CostSnapshot.team_id == team_id,
                CostSnapshot.date >= start_date,
                CostSnapshot.date <= end_date,
            )
            .group_by(CostSnapshot.date)
            .order_by(CostSnapshot.date)
        ).all()
    
    def _forecast_daily_costs(
        self,
        daily_costs: List[float],
        *,
        method: str,
        horizon_days: int
    ) -> List[float]:
        values = np.array(daily_costs, dtype=float)
        if len(values) < 3:
            return [float(values[-1])] * horizon_days
        
        method = method.lower()
        if method == "arima":
            forecast = self._arima_forecast(values, horizon_days)
            if forecast is not None:
                return forecast
            logger.warning("ARIMA failed, falling back to ETS.")
        
        return self._ets_forecast(values, horizon_days)
    
    @staticmethod
    def _ets_forecast(values: np.ndarray, horizon_days: int) -> List[float]:
        # Holt's linear trend method (ETS)
        alpha = 0.4
        beta = 0.2
        level = values[0]
        trend = values[1] - values[0] if len(values) > 1 else 0.0
        for v in values[1:]:
            prev_level = level
            level = alpha * v + (1 - alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend
        forecast = [max(0.0, level + (i + 1) * trend) for i in range(horizon_days)]
        return forecast
    
    @staticmethod
    def _arima_forecast(values: np.ndarray, horizon_days: int) -> Optional[List[float]]:
        try:
            from statsmodels.tsa.arima.model import ARIMA
        except Exception:
            return None
        try:
            model = ARIMA(values, order=(1, 0, 1))
            fit = model.fit()
            forecast = fit.forecast(steps=horizon_days)
            return [max(0.0, float(v)) for v in forecast]
        except Exception:
            return None
    
    def _cost_breakdown(
        self,
        team_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Tuple[List[Dict], float]:
        job_stmt = (
            select(
                func.date(Job.start_time).label("day"),
                Job.job_type,
                Job.model_name,
                Job.environment,
                func.count(Job.id).label("job_count"),
            )
            .where(
                Job.team_id == team_id,
                Job.start_time.isnot(None),
                func.date(Job.start_time) >= start_date,
                func.date(Job.start_time) <= end_date,
            )
            .group_by("day", Job.job_type, Job.model_name, Job.environment)
        )
        job_rows = self.db.execute(job_stmt).all()
        if not job_rows:
            return [], 0.0
        
        daily_costs = {
            str(day): total for day, total in self._fetch_daily_costs(team_id, start_date, end_date)
        }
        if not daily_costs:
            return [], 0.0
        
        day_totals: Dict[date, int] = {}
        for row in job_rows:
            day_key = str(row.day)
            day_totals[day_key] = day_totals.get(day_key, 0) + int(row.job_count)
        
        allocation: Dict[str, float] = {}
        
        for row in job_rows:
            day_key = str(row.day)
            day_cost = float(daily_costs.get(day_key, 0.0))
            total_jobs = day_totals.get(day_key, 0)
            if day_cost <= 0 or row.job_count <= 0 or total_jobs <= 0:
                continue
            key = f"{row.job_type or 'unknown'}|{row.model_name}|{row.environment or 'unknown'}"
            share = day_cost * (row.job_count / total_jobs)
            allocation[key] = allocation.get(key, 0.0) + share
        
        if not allocation:
            return [], 0.0
        
        total_cost = sum(allocation.values())
        breakdown = []
        for key, value in allocation.items():
            job_type, model_name, environment = key.split("|", 2)
            breakdown.append({
                "job_type": job_type,
                "model_name": model_name,
                "environment": environment,
                "total_cost": round(value, 2),
                "share_of_total": round(value / total_cost, 4) if total_cost > 0 else 0.0
            })
        breakdown.sort(key=lambda item: item["total_cost"], reverse=True)
        return breakdown, total_cost
    
    @staticmethod
    def _correlation_risk_from_breakdown(breakdown: List[Dict], total_cost: float) -> float:
        if total_cost <= 0 or not breakdown:
            return 0.0
        concentration = max(item["share_of_total"] for item in breakdown)
        return min(1.0, concentration)
