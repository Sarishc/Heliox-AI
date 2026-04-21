"""Predictive capacity & workload scheduling engine."""

import logging
from datetime import timedelta
from typing import Dict, Optional
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.services.forecasting import ForecastingService, MIN_DATA_POINTS_FOR_FORECAST

logger = logging.getLogger(__name__)


class SchedulingForecastService:
    """
    Forecast GPU demand and recommend capacity windows.
    """

    def __init__(self, db: Session):
        self.db = db
        self.forecast_service = ForecastingService(db, redis_client=None)

    def forecast(
        self,
        *,
        team_id: UUID,
        horizon_days: int,
        provider: Optional[str] = None,
        gpu_type: Optional[str] = None,
    ) -> Dict:
        history = self.forecast_service._fetch_usage_history(team_id, provider, gpu_type)
        if len(history) < MIN_DATA_POINTS_FOR_FORECAST:
            return {
                "error": (
                    f"Insufficient historical data. Need at least "
                    f"{MIN_DATA_POINTS_FOR_FORECAST} days, found {len(history)}."
                ),
                "projections": [],
            }

        start_date = history[0][0]
        end_date = history[-1][0]
        history_filled = self.forecast_service._fill_missing_dates(history, start_date, end_date)
        values = np.array([v for _, v in history_filled], dtype=float)

        # Exponential smoothing
        alpha = 0.3
        smoothed = values[0]
        for v in values[1:]:
            smoothed = alpha * v + (1 - alpha) * smoothed

        # Simple trend based on last 7 days
        window = min(7, len(values))
        recent = values[-window:]
        slope = 0.0
        if window > 1:
            x = np.arange(window)
            slope = np.polyfit(x, recent, 1)[0]

        # Infer capacity as 95th percentile of historical usage
        capacity_hours = float(np.percentile(values, 95))
        capacity_gpus = capacity_hours / 24.0 if capacity_hours > 0 else 1.0

        projections = []
        for i in range(horizon_days):
            forecast_hours = max(0.0, smoothed + slope * (i + 1))
            required_gpus = forecast_hours / 24.0
            utilization = min(1.5, forecast_hours / capacity_hours) if capacity_hours > 0 else 0.0
            congestion_probability = self._congestion_probability(utilization)
            projections.append(
                {
                    "date": str(end_date + timedelta(days=i + 1)),
                    "required_gpus": round(required_gpus, 2),
                    "utilization_projection": round(utilization, 2),
                    "congestion_probability": round(congestion_probability, 2),
                }
            )

        return {
            "horizon_days": horizon_days,
            "capacity_gpus": round(capacity_gpus, 2),
            "projections": projections,
        }

    @staticmethod
    def _congestion_probability(utilization: float) -> float:
        if utilization <= 0.85:
            return 0.1 * utilization
        return min(1.0, 0.5 + (utilization - 0.85) / 0.15 * 0.5)
