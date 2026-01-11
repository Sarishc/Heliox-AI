"""Daily digest generation service."""
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.alert_settings import AlertSettings
from app.models.cost import CostSnapshot
from app.models.team import Team
from app.schemas.alert_settings import DailyDigestPayload, DailyDigestTeamData
from app.schemas.recommendation import RecommendationFilters
from app.services.recommendations import RecommendationEngine

logger = logging.getLogger(__name__)


class DailyDigestGenerator:
    """Service for generating daily digest payloads."""
    
    def __init__(self, db: Session):
        self.db = db
        self.rec_engine = RecommendationEngine(db)
    
    def _get_cost_for_period(
        self,
        start_date: date,
        end_date: date
    ) -> float:
        """
        Get total cost for a period.
        
        Note: CostSnapshot is infrastructure-level, no team attribution.
        """
        query = select(func.sum(CostSnapshot.cost_usd)).where(
            CostSnapshot.date >= start_date,
            CostSnapshot.date <= end_date
        )
        
        result = self.db.execute(query).scalar_one_or_none()
        return float(result) if result else 0.0
    
    def _get_top_gpu_types(
        self,
        start_date: date,
        end_date: date,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get top GPU types by cost for a period.
        
        Simplified: Returns top (provider, gpu_type) combinations by total cost.
        """
        query = select(
            CostSnapshot.provider,
            CostSnapshot.gpu_type,
            func.sum(CostSnapshot.cost_usd).label("cost")
        ).where(
            CostSnapshot.date >= start_date,
            CostSnapshot.date <= end_date
        ).group_by(
            CostSnapshot.provider,
            CostSnapshot.gpu_type
        ).order_by(
            desc("cost")
        ).limit(limit)
        
        result = self.db.execute(query).all()
        
        return [
            {
                "gpu_type": f"{row.gpu_type.upper()} ({row.provider.upper()})",
                "cost": float(row.cost)
            }
            for row in result
        ]
    
    def generate_daily_digest(
        self,
        target_date: date = None
    ) -> DailyDigestPayload:
        """
        Generate simplified daily digest payload.
        
        YC-safe approach: total spend + trend + top GPU types.
        No team/model breakdown (simplified for MVP).
        
        Args:
            target_date: Date for the digest (defaults to yesterday)
            
        Returns:
            DailyDigestPayload
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        logger.info(f"Generating daily digest for {target_date}")
        
        # Calculate date ranges
        yesterday = target_date
        day_before = yesterday - timedelta(days=1)
        week_ago = yesterday - timedelta(days=7)
        month_ago = yesterday - timedelta(days=30)
        
        # Get global costs (infrastructure-level only)
        total_daily_cost = self._get_cost_for_period(yesterday, yesterday)
        total_weekly_cost = self._get_cost_for_period(week_ago, yesterday)
        total_monthly_cost = self._get_cost_for_period(month_ago, yesterday)
        
        # Calculate daily trend (vs previous day)
        previous_daily = self._get_cost_for_period(day_before, day_before)
        daily_change_percent = 0.0
        if previous_daily > 0:
            daily_change_percent = ((total_daily_cost - previous_daily) / previous_daily) * 100
        
        # Get top GPU types (simplified: no model attribution)
        global_top_gpu_types = self._get_top_gpu_types(yesterday, yesterday, limit=5)
        
        # Get global recommendations
        filters = RecommendationFilters(
            start_date=yesterday - timedelta(days=14),
            end_date=yesterday
        )
        response = self.rec_engine.generate_recommendations(filters)
        all_recommendations = response.recommendations
        
        # Sort by savings and get top 5
        sorted_recs = sorted(
            all_recommendations,
            key=lambda x: x.estimated_savings_usd,
            reverse=True
        )[:5]
        
        global_recommendations = [
            {
                "title": rec.title,
                "savings": rec.estimated_savings_usd,
                "severity": rec.severity.value,
                "description": rec.description
            }
            for rec in sorted_recs
        ]
        
        # Calculate global potential savings
        global_potential_savings = sum(
            rec.estimated_savings_usd
            for rec in all_recommendations
        )
        
        # Format top GPU types as "models" for schema compatibility
        # (Schema expects top_models, but we're providing top GPU types)
        global_top_models = [
            {"model_name": item["gpu_type"], "cost": item["cost"]}
            for item in global_top_gpu_types
        ]
        
        # Return simplified digest (no team breakdown for MVP)
        # Teams array is empty - team attribution requires Jobs JOIN (future enhancement)
        return DailyDigestPayload(
            date=str(target_date),
            total_daily_cost=total_daily_cost,
            total_weekly_cost=total_weekly_cost,
            total_monthly_cost=total_monthly_cost,
            teams=[],  # Simplified: no team breakdown yet
            global_top_models=global_top_models,  # Actually top GPU types
            global_recommendations=global_recommendations,
            global_potential_savings=global_potential_savings
        )
