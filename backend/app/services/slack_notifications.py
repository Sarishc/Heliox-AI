"""Slack notification service for Heliox alerts."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal

import httpx
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cost import CostSnapshot
from app.schemas.recommendation import RecommendationFilters, RecommendationSeverity, RecommendationType
from app.services.recommendations import RecommendationEngine

settings = get_settings()
logger = logging.getLogger(__name__)

# Configuration
SLACK_TIMEOUT = 10  # seconds
SLACK_MAX_RETRIES = 3
BURN_RATE_THRESHOLD_USD = 10000  # Daily spend threshold for alerts


class SlackNotificationService:
    """Service for sending Slack notifications."""
    
    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Slack notification service.
        
        Args:
            webhook_url: Slack webhook URL. If not provided, uses settings.
        """
        self.webhook_url = webhook_url or settings.SLACK_WEBHOOK_URL
        self.enabled = bool(self.webhook_url)
        
        if not self.enabled:
            logger.warning("Slack notifications disabled: SLACK_WEBHOOK_URL not configured")
    
    def _mask_webhook_url(self, url: str) -> str:
        """Mask webhook URL for safe logging."""
        if not url:
            return "None"
        # Show only last 8 characters
        return f"***{url[-8:]}"
    
    async def _send_slack_message(self, blocks: List[Dict], text: str) -> bool:
        """
        Send a message to Slack using webhook.
        
        Args:
            blocks: Slack Block Kit blocks
            text: Fallback text for notifications
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.info("Slack notification skipped (not configured)")
            return False
        
        payload = {
            "text": text,
            "blocks": blocks
        }
        
        async with httpx.AsyncClient(timeout=SLACK_TIMEOUT) as client:
            for attempt in range(1, SLACK_MAX_RETRIES + 1):
                try:
                    response = await client.post(
                        self.webhook_url,
                        json=payload
                    )
                    
                    if response.status_code == 200:
                        logger.info(
                            f"Slack notification sent successfully "
                            f"(webhook: {self._mask_webhook_url(self.webhook_url)})"
                        )
                        return True
                    else:
                        logger.warning(
                            f"External service failure: Slack notification failed (attempt {attempt}/{SLACK_MAX_RETRIES}): "
                            f"status={response.status_code}",
                            extra={"service": "slack", "status_code": response.status_code, "attempt": attempt}
                        )
                        
                except httpx.TimeoutException:
                    logger.warning(
                        f"External service failure: Slack notification timeout (attempt {attempt}/{SLACK_MAX_RETRIES})",
                        extra={"service": "slack", "error_type": "timeout", "attempt": attempt},
                        exc_info=True
                    )
                except Exception as e:
                    logger.warning(
                        f"External service failure: Slack notification error (attempt {attempt}/{SLACK_MAX_RETRIES}): {type(e).__name__}",
                        exc_info=True,
                        extra={"service": "slack", "error_type": type(e).__name__, "attempt": attempt}
                    )
                
                # Wait before retry (exponential backoff)
                if attempt < SLACK_MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)
        
        logger.warning(
            "External service failure: Slack notification failed after all retries",
            extra={"service": "slack", "retries": SLACK_MAX_RETRIES}
        )
        return False
    
    def _format_currency(self, amount: float) -> str:
        """Format currency for display."""
        return f"${amount:,.2f}"
    
    def _create_burn_rate_alert_blocks(
        self,
        daily_cost: float,
        threshold: float,
        date: str
    ) -> List[Dict]:
        """Create Slack blocks for burn rate alert."""
        percentage_over = ((daily_cost - threshold) / threshold) * 100
        
        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔥 High Burn Rate Alert",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Daily GPU spending has exceeded the threshold!*\n\n"
                        f"• *Date:* {date}\n"
                        f"• *Daily Cost:* {self._format_currency(daily_cost)}\n"
                        f"• *Threshold:* {self._format_currency(threshold)}\n"
                        f"• *Over by:* {self._format_currency(daily_cost - threshold)} "
                        f"({percentage_over:.1f}%)"
                    )
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 Review your GPU usage to identify cost drivers"
                    }
                ]
            }
        ]
    
    def _create_idle_spend_alert_blocks(
        self,
        recommendations: List[Dict]
    ) -> List[Dict]:
        """Create Slack blocks for idle spend alert."""
        total_idle_savings = sum(
            rec.get("estimated_savings_usd", 0)
            for rec in recommendations
        )
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ Idle GPU Spend Detected",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*High-severity idle spend recommendations found!*\n\n"
                        f"• *Total Potential Savings:* {self._format_currency(total_idle_savings)}/month\n"
                        f"• *Number of Issues:* {len(recommendations)}"
                    )
                }
            },
            {
                "type": "divider"
            }
        ]
        
        # Add individual recommendations
        for i, rec in enumerate(recommendations[:3], 1):  # Limit to 3 for brevity
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{i}. {rec['title']}*\n"
                        f"{rec['description']}\n"
                        f"💰 Savings: {self._format_currency(rec['estimated_savings_usd'])}/month"
                    )
                }
            })
        
        if len(recommendations) > 3:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_+{len(recommendations) - 3} more recommendations available in dashboard_"
                    }
                ]
            })
        
        return blocks
    
    def _create_daily_summary_blocks(
        self,
        daily_cost: float,
        weekly_cost: float,
        monthly_cost: float,
        top_models: List[Dict],
        high_severity_count: int,
        total_savings: float
    ) -> List[Dict]:
        """Create Slack blocks for daily summary."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Heliox Daily Summary",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Yesterday:*\n{self._format_currency(daily_cost)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Last 7 Days:*\n{self._format_currency(weekly_cost)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Last 30 Days:*\n{self._format_currency(monthly_cost)}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Potential Savings:*\n{self._format_currency(total_savings)}/mo"
                    }
                ]
            }
        ]
        
        # Top models
        if top_models:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Top GPU Consumers (Yesterday):*"
                }
            })
            
            for model in top_models[:3]:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {model['model_name']}: {self._format_currency(model['cost'])}"
                    }
                })
        
        # Recommendations summary
        if high_severity_count > 0:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"⚠️ *{high_severity_count} high-severity recommendations* available\n"
                        f"Review them in your Heliox dashboard"
                    )
                }
            })
        
        return blocks
    
    async def send_burn_rate_alert(
        self,
        daily_cost: float,
        threshold: float,
        date: str
    ) -> bool:
        """
        Send burn rate alert to Slack.
        
        Args:
            daily_cost: Daily GPU cost
            threshold: Cost threshold
            date: Date string (YYYY-MM-DD)
            
        Returns:
            True if sent successfully
        """
        logger.info(
            f"Sending burn rate alert: daily_cost=${daily_cost:.2f}, "
            f"threshold=${threshold:.2f}, date={date}"
        )
        
        blocks = self._create_burn_rate_alert_blocks(daily_cost, threshold, date)
        text = f"High Burn Rate Alert: ${daily_cost:.2f} spent on {date}"
        
        return await self._send_slack_message(blocks, text)
    
    async def send_idle_spend_alert(
        self,
        recommendations: List[Dict]
    ) -> bool:
        """
        Send idle spend alert to Slack.
        
        Args:
            recommendations: List of high-severity recommendations
            
        Returns:
            True if sent successfully
        """
        logger.info(f"Sending idle spend alert: {len(recommendations)} recommendations")
        
        blocks = self._create_idle_spend_alert_blocks(recommendations)
        text = f"Idle GPU Spend Alert: {len(recommendations)} high-severity issues found"
        
        return await self._send_slack_message(blocks, text)
    
    async def send_daily_summary(
        self,
        daily_cost: float,
        weekly_cost: float,
        monthly_cost: float,
        top_models: List[Dict],
        high_severity_count: int,
        total_savings: float
    ) -> bool:
        """
        Send daily summary to Slack.
        
        Args:
            daily_cost: Yesterday's cost
            weekly_cost: Last 7 days cost
            monthly_cost: Last 30 days cost
            top_models: Top GPU consuming models
            high_severity_count: Number of high severity recommendations
            total_savings: Total potential savings
            
        Returns:
            True if sent successfully
        """
        logger.info("Sending daily summary")
        
        blocks = self._create_daily_summary_blocks(
            daily_cost,
            weekly_cost,
            monthly_cost,
            top_models,
            high_severity_count,
            total_savings
        )
        text = f"Heliox Daily Summary: ${daily_cost:.2f} spent yesterday"
        
        return await self._send_slack_message(blocks, text)


async def check_and_send_burn_rate_alert(db: Session, date_str: Optional[str] = None) -> bool:
    """
    Check if burn rate exceeds threshold and send alert.
    
    Args:
        db: Database session
        date_str: Date to check (YYYY-MM-DD). Defaults to yesterday.
        
    Returns:
        True if alert was sent
    """
    from datetime import date, timedelta
    
    # Default to yesterday
    if date_str is None:
        check_date = date.today() - timedelta(days=1)
        date_str = check_date.strftime("%Y-%m-%d")
    
    # Get daily cost
    query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.date == date_str
    )
    result = db.execute(query).scalar_one_or_none()
    daily_cost = float(result) if result else 0.0
    
    logger.info(f"Daily cost for {date_str}: ${daily_cost:.2f}")
    
    # Check threshold
    if daily_cost > BURN_RATE_THRESHOLD_USD:
        slack_service = SlackNotificationService()
        return await slack_service.send_burn_rate_alert(
            daily_cost,
            BURN_RATE_THRESHOLD_USD,
            date_str
        )
    
    logger.info(f"Burn rate OK: ${daily_cost:.2f} <= ${BURN_RATE_THRESHOLD_USD}")
    return False


async def check_and_send_idle_spend_alert(db: Session) -> bool:
    """
    Check for high-severity idle spend recommendations and send alert.
    
    Args:
        db: Database session
        
    Returns:
        True if alert was sent
    """
    from datetime import date, timedelta
    
    # Get recommendations for last 14 days
    end_date = date.today()
    start_date = end_date - timedelta(days=14)
    
    # Create filters for high-severity idle GPU recommendations
    filters = RecommendationFilters(
        start_date=start_date,
        end_date=end_date,
        min_severity=RecommendationSeverity.HIGH,
        types=[RecommendationType.IDLE_GPU]
    )
    
    rec_engine = RecommendationEngine(db)
    response = rec_engine.generate_recommendations(filters)
    
    # Convert Recommendation objects to dicts
    idle_recommendations = [rec.model_dump() for rec in response.recommendations]
    
    logger.info(f"Found {len(idle_recommendations)} high-severity idle spend recommendations")
    
    if idle_recommendations:
        slack_service = SlackNotificationService()
        return await slack_service.send_idle_spend_alert(idle_recommendations)
    
    logger.info("No high-severity idle spend detected")
    return False


async def send_daily_summary_report(db: Session) -> bool:
    """
    Generate and send daily summary report.
    
    Args:
        db: Database session
        
    Returns:
        True if sent successfully
    """
    from datetime import date, timedelta
    from sqlalchemy import desc
    
    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Get cost summaries
    yesterday_query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.date == yesterday
    )
    daily_cost = float(db.execute(yesterday_query).scalar_one_or_none() or 0)
    
    weekly_query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.date >= week_ago
    )
    weekly_cost = float(db.execute(weekly_query).scalar_one_or_none() or 0)
    
    monthly_query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.date >= month_ago
    )
    monthly_cost = float(db.execute(monthly_query).scalar_one_or_none() or 0)
    
    # Get top GPU types from yesterday (simplified: no model attribution)
    top_gpu_query = select(
        CostSnapshot.provider,
        CostSnapshot.gpu_type,
        func.sum(CostSnapshot.cost_usd).label("cost")
    ).where(
        CostSnapshot.date == yesterday
    ).group_by(
        CostSnapshot.provider,
        CostSnapshot.gpu_type
    ).order_by(
        desc("cost")
    ).limit(3)
    
    top_gpu_result = db.execute(top_gpu_query).all()
    top_models = [
        {"model_name": f"{row.gpu_type.upper()} ({row.provider.upper()})", "cost": float(row.cost)}
        for row in top_gpu_result
    ]
    
    # Get recommendations
    filters = RecommendationFilters(
        start_date=yesterday - timedelta(days=14),
        end_date=yesterday,
        min_severity=RecommendationSeverity.HIGH
    )
    rec_engine = RecommendationEngine(db)
    response = rec_engine.generate_recommendations(filters)
    
    high_severity_count = len(response.recommendations)
    total_savings = sum(rec.estimated_savings_usd for rec in response.recommendations)
    
    # Send summary
    slack_service = SlackNotificationService()
    return await slack_service.send_daily_summary(
        daily_cost,
        weekly_cost,
        monthly_cost,
        top_models,
        high_severity_count,
        total_savings
    )

