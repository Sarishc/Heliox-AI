"""Forecasting service for GPU usage and cost predictions."""
import hashlib
import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot, UsageSnapshot

logger = logging.getLogger(__name__)

# Forecasting configuration
MIN_DATA_POINTS_FOR_ML = 30  # Minimum days for ML models
MIN_DATA_POINTS_FOR_FORECAST = 7  # Minimum days for any forecast
DEFAULT_HORIZON_DAYS = 7
MAX_HORIZON_DAYS = 30
CACHE_TTL_SECONDS = 3600  # 1 hour


class ForecastingService:
    """
    Service for generating usage and cost forecasts.
    
    Uses a tiered approach:
    1. Simple moving average + trend for small datasets (< 30 days)
    2. LightGBM for larger datasets (>= 30 days) if available
    3. Always includes confidence bands based on historical volatility
    """
    
    def __init__(self, db_session: Session, redis_client=None):
        self.db = db_session
        self.redis = redis_client
        
    def _generate_cache_key(
        self,
        forecast_type: str,
        provider: Optional[str],
        gpu_type: Optional[str],
        horizon_days: int
    ) -> str:
        """Generate cache key for forecast results."""
        key_data = {
            "type": forecast_type,
            "provider": provider or "all",
            "gpu_type": gpu_type or "all",
            "horizon": horizon_days
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return f"forecast:{hashlib.md5(key_str.encode()).hexdigest()}"
    
    def _get_cached_forecast(self, cache_key: str) -> Optional[Dict]:
        """Retrieve cached forecast if available."""
        if not self.redis:
            return None
        
        try:
            cached = self.redis.get(cache_key)
            if cached:
                logger.info(f"Cache hit for forecast: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis cache read error: {e}")
        
        return None
    
    def _cache_forecast(self, cache_key: str, forecast_data: Dict) -> None:
        """Cache forecast results."""
        if not self.redis:
            return
        
        try:
            self.redis.setex(
                cache_key,
                CACHE_TTL_SECONDS,
                json.dumps(forecast_data, default=str)
            )
            logger.info(f"Cached forecast: {cache_key}")
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")
    
    def _fetch_usage_history(
        self,
        provider: Optional[str],
        gpu_type: Optional[str]
    ) -> List[Tuple[date, float]]:
        """Fetch historical usage data."""
        query = select(
            UsageSnapshot.date,
            func.sum(UsageSnapshot.gpu_hours).label("total_hours")
        ).group_by(UsageSnapshot.date).order_by(UsageSnapshot.date)
        
        if provider:
            query = query.where(UsageSnapshot.provider == provider.lower())
        if gpu_type:
            query = query.where(UsageSnapshot.gpu_type == gpu_type.lower())
        
        result = self.db.execute(query).all()
        return [(row.date, float(row.total_hours)) for row in result]
    
    def _fetch_cost_history(
        self,
        provider: Optional[str],
        gpu_type: Optional[str]
    ) -> List[Tuple[date, float]]:
        """Fetch historical cost data."""
        query = select(
            CostSnapshot.date,
            func.sum(CostSnapshot.cost_usd).label("total_cost")
        ).group_by(CostSnapshot.date).order_by(CostSnapshot.date)
        
        if provider:
            query = query.where(CostSnapshot.provider == provider.lower())
        if gpu_type:
            query = query.where(CostSnapshot.gpu_type == gpu_type.lower())
        
        result = self.db.execute(query).all()
        return [(row.date, float(row.total_cost)) for row in result]
    
    def _fill_missing_dates(
        self,
        data: List[Tuple[date, float]],
        start_date: date,
        end_date: date
    ) -> List[Tuple[date, float]]:
        """Fill missing dates with interpolated values."""
        if not data:
            return []
        
        # Create a dict for quick lookup
        data_dict = dict(data)
        
        # Fill all dates in range
        filled = []
        current_date = start_date
        while current_date <= end_date:
            if current_date in data_dict:
                filled.append((current_date, data_dict[current_date]))
            else:
                # Simple forward fill (use last known value)
                if filled:
                    filled.append((current_date, filled[-1][1]))
                else:
                    filled.append((current_date, 0.0))
            current_date += timedelta(days=1)
        
        return filled
    
    def _moving_average_forecast(
        self,
        historical_values: np.ndarray,
        horizon: int,
        window: int = 7
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Simple moving average with linear trend forecast.
        
        Returns:
            forecast: Point forecast
            lower_bound: Lower confidence bound
            upper_bound: Upper confidence bound
        """
        n = len(historical_values)
        
        # Calculate moving average
        if n < window:
            window = max(3, n // 2)
        
        ma = np.convolve(historical_values, np.ones(window) / window, mode='valid')
        
        # Calculate linear trend on recent data
        recent_window = min(14, n)
        recent_values = historical_values[-recent_window:]
        x = np.arange(len(recent_values))
        
        # Simple linear regression
        if len(x) > 1:
            slope = np.polyfit(x, recent_values, 1)[0]
        else:
            slope = 0
        
        # Generate forecast
        last_value = historical_values[-1]
        forecast = np.array([last_value + slope * (i + 1) for i in range(horizon)])
        
        # Ensure non-negative forecasts
        forecast = np.maximum(forecast, 0)
        
        # Calculate confidence bands based on historical volatility
        # Use standard deviation of recent changes
        if n > 1:
            changes = np.diff(historical_values[-recent_window:])
            std = np.std(changes) if len(changes) > 0 else 0
        else:
            std = 0
        
        # Confidence bands widen over time
        confidence_multiplier = np.sqrt(np.arange(1, horizon + 1))
        lower_bound = forecast - 1.96 * std * confidence_multiplier
        upper_bound = forecast + 1.96 * std * confidence_multiplier
        
        # Ensure non-negative bounds
        lower_bound = np.maximum(lower_bound, 0)
        upper_bound = np.maximum(upper_bound, forecast)
        
        return forecast, lower_bound, upper_bound
    
    def _lightgbm_forecast(
        self,
        historical_values: np.ndarray,
        horizon: int
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        LightGBM-based forecast for larger datasets.
        
        Falls back to moving average if LightGBM is not available or fails.
        """
        try:
            import lightgbm as lgb
            
            # Prepare features: lag features and time features
            n = len(historical_values)
            
            # Create lag features
            lags = [1, 2, 3, 7, 14] if n > 14 else [1, 2, 3]
            X = []
            y = []
            
            for i in range(max(lags), n):
                features = []
                for lag in lags:
                    features.append(historical_values[i - lag])
                # Add day of week feature (simple proxy using position)
                features.append(i % 7)
                X.append(features)
                y.append(historical_values[i])
            
            if len(X) < 10:  # Not enough data for ML
                logger.info("Not enough data for LightGBM, using moving average")
                return self._moving_average_forecast(historical_values, horizon)
            
            X = np.array(X)
            y = np.array(y)
            
            # Train model
            train_data = lgb.Dataset(X, label=y)
            params = {
                'objective': 'regression',
                'metric': 'rmse',
                'verbosity': -1,
                'num_leaves': 15,
                'learning_rate': 0.05,
                'feature_fraction': 0.8
            }
            
            model = lgb.train(
                params,
                train_data,
                num_boost_round=50,
                valid_sets=[train_data],
                callbacks=[lgb.early_stopping(10, verbose=False)]
            )
            
            # Generate forecast
            forecast = []
            last_values = list(historical_values[-max(lags):])
            
            for i in range(horizon):
                features = []
                for lag in lags:
                    if lag <= len(last_values):
                        features.append(last_values[-lag])
                    else:
                        features.append(last_values[0])
                features.append((n + i) % 7)
                
                pred = model.predict([features])[0]
                pred = max(0, pred)  # Ensure non-negative
                forecast.append(pred)
                last_values.append(pred)
            
            forecast = np.array(forecast)
            
            # Calculate confidence bands based on model's historical performance
            # Use RMSE from training as uncertainty estimate
            y_pred = model.predict(X)
            rmse = np.sqrt(np.mean((y - y_pred) ** 2))
            
            confidence_multiplier = np.sqrt(np.arange(1, horizon + 1))
            lower_bound = forecast - 1.96 * rmse * confidence_multiplier
            upper_bound = forecast + 1.96 * rmse * confidence_multiplier
            
            lower_bound = np.maximum(lower_bound, 0)
            upper_bound = np.maximum(upper_bound, forecast)
            
            return forecast, lower_bound, upper_bound
            
        except ImportError:
            logger.info("LightGBM not available, using moving average")
            return self._moving_average_forecast(historical_values, horizon)
        except Exception as e:
            logger.warning(f"LightGBM forecast failed: {e}, falling back to moving average")
            return self._moving_average_forecast(historical_values, horizon)
    
    def forecast_usage(
        self,
        provider: Optional[str] = None,
        gpu_type: Optional[str] = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS
    ) -> Dict:
        """
        Generate GPU usage forecast.
        
        Args:
            provider: Filter by provider (e.g., 'aws', 'gcp')
            gpu_type: Filter by GPU type (e.g., 'a100', 'h100')
            horizon_days: Number of days to forecast (1-30)
            
        Returns:
            Dictionary with historical and forecast data
        """
        # Validate inputs
        horizon_days = max(1, min(horizon_days, MAX_HORIZON_DAYS))
        
        # Check cache
        cache_key = self._generate_cache_key("usage", provider, gpu_type, horizon_days)
        cached = self._get_cached_forecast(cache_key)
        if cached:
            return cached
        
        # Fetch historical data
        logger.info(f"Generating usage forecast: provider={provider}, gpu_type={gpu_type}, horizon={horizon_days}")
        history = self._fetch_usage_history(provider, gpu_type)
        
        if len(history) < MIN_DATA_POINTS_FOR_FORECAST:
            logger.warning(f"Insufficient data for forecast: {len(history)} days")
            return {
                "error": f"Insufficient historical data. Need at least {MIN_DATA_POINTS_FOR_FORECAST} days, found {len(history)}.",
                "historical": [],
                "forecast": []
            }
        
        # Fill missing dates
        start_date = history[0][0]
        end_date = history[-1][0]
        history_filled = self._fill_missing_dates(history, start_date, end_date)
        
        # Extract values
        dates = [d for d, _ in history_filled]
        values = np.array([v for _, v in history_filled])
        
        # Generate forecast
        if len(values) >= MIN_DATA_POINTS_FOR_ML:
            logger.info("Using LightGBM forecast")
            forecast_values, lower, upper = self._lightgbm_forecast(values, horizon_days)
        else:
            logger.info("Using moving average forecast")
            forecast_values, lower, upper = self._moving_average_forecast(values, horizon_days)
        
        # Generate forecast dates
        forecast_start = end_date + timedelta(days=1)
        forecast_dates = [forecast_start + timedelta(days=i) for i in range(horizon_days)]
        
        # Build response
        result = {
            "provider": provider,
            "gpu_type": gpu_type,
            "horizon_days": horizon_days,
            "forecast_method": "lightgbm" if len(values) >= MIN_DATA_POINTS_FOR_ML else "moving_average",
            "historical": [
                {
                    "date": str(d),
                    "value": float(v)
                }
                for d, v in zip(dates, values)
            ],
            "forecast": [
                {
                    "date": str(d),
                    "value": float(forecast_values[i]),
                    "lower_bound": float(lower[i]),
                    "upper_bound": float(upper[i])
                }
                for i, d in enumerate(forecast_dates)
            ],
            "metadata": {
                "historical_data_points": len(values),
                "forecast_generated_at": str(date.today())
            }
        }
        
        # Cache result
        self._cache_forecast(cache_key, result)
        
        return result
    
    def forecast_spend(
        self,
        provider: Optional[str] = None,
        gpu_type: Optional[str] = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS
    ) -> Dict:
        """
        Generate GPU cost forecast.
        
        Args:
            provider: Filter by provider (e.g., 'aws', 'gcp')
            gpu_type: Filter by GPU type (e.g., 'a100', 'h100')
            horizon_days: Number of days to forecast (1-30)
            
        Returns:
            Dictionary with historical and forecast data
        """
        # Validate inputs
        horizon_days = max(1, min(horizon_days, MAX_HORIZON_DAYS))
        
        # Check cache
        cache_key = self._generate_cache_key("spend", provider, gpu_type, horizon_days)
        cached = self._get_cached_forecast(cache_key)
        if cached:
            return cached
        
        # Fetch historical data
        logger.info(f"Generating spend forecast: provider={provider}, gpu_type={gpu_type}, horizon={horizon_days}")
        history = self._fetch_cost_history(provider, gpu_type)
        
        if len(history) < MIN_DATA_POINTS_FOR_FORECAST:
            logger.warning(f"Insufficient data for forecast: {len(history)} days")
            return {
                "error": f"Insufficient historical data. Need at least {MIN_DATA_POINTS_FOR_FORECAST} days, found {len(history)}.",
                "historical": [],
                "forecast": []
            }
        
        # Fill missing dates
        start_date = history[0][0]
        end_date = history[-1][0]
        history_filled = self._fill_missing_dates(history, start_date, end_date)
        
        # Extract values
        dates = [d for d, _ in history_filled]
        values = np.array([v for _, v in history_filled])
        
        # Generate forecast
        if len(values) >= MIN_DATA_POINTS_FOR_ML:
            logger.info("Using LightGBM forecast")
            forecast_values, lower, upper = self._lightgbm_forecast(values, horizon_days)
        else:
            logger.info("Using moving average forecast")
            forecast_values, lower, upper = self._moving_average_forecast(values, horizon_days)
        
        # Generate forecast dates
        forecast_start = end_date + timedelta(days=1)
        forecast_dates = [forecast_start + timedelta(days=i) for i in range(horizon_days)]
        
        # Build response
        result = {
            "provider": provider,
            "gpu_type": gpu_type,
            "horizon_days": horizon_days,
            "forecast_method": "lightgbm" if len(values) >= MIN_DATA_POINTS_FOR_ML else "moving_average",
            "historical": [
                {
                    "date": str(d),
                    "value": float(v)
                }
                for d, v in zip(dates, values)
            ],
            "forecast": [
                {
                    "date": str(d),
                    "value": float(forecast_values[i]),
                    "lower_bound": float(lower[i]),
                    "upper_bound": float(upper[i])
                }
                for i, d in enumerate(forecast_dates)
            ],
            "metadata": {
                "historical_data_points": len(values),
                "forecast_generated_at": str(date.today())
            }
        }
        
        # Cache result
        self._cache_forecast(cache_key, result)
        
        return result

