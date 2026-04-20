"""Slack notification service for Heliox alerts."""
import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional
from uuid import UUID
from decimal import Decimal

import httpx
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.cost import CostSnapshot
from app.models.alert_settings import AlertSettings
from app.models.budget import BudgetPolicy
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

    async def send_budget_alert(
        self,
        *,
        policy: BudgetPolicy,
        mtd_spend: float,
        forecasted_eom_spend: float,
        percent_used: float,
        predicted_breach_date: Optional[date],
    ) -> bool:
        """Send budget guardrail alert."""
        env_label = policy.environment.value
        project_label = policy.project or "all"
        breach_text = (
            predicted_breach_date.isoformat() if predicted_breach_date else "not projected"
        )
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Budget Guardrail Alert*"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Environment:*\n{env_label}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{project_label}"},
                    {"type": "mrkdwn", "text": f"*Budget:*\n{self._format_currency(float(policy.monthly_budget_usd))}"},
                    {"type": "mrkdwn", "text": f"*MTD Spend:*\n{self._format_currency(mtd_spend)}"},
                    {"type": "mrkdwn", "text": f"*Used:*\n{percent_used * 100:.0f}%"},
                    {"type": "mrkdwn", "text": f"*Forecast EOM:*\n{self._format_currency(forecasted_eom_spend)}"},
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Predicted breach date: {breach_text}",
                    }
                ],
            },
        ]
        text = f"Budget Guardrail: {percent_used * 100:.0f}% used ({env_label})"
        return await self._send_slack_message(blocks, text)

    def _create_anomaly_alert_blocks(self, anomalies: List[Dict]) -> List[Dict]:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Anomaly Detected", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{len(anomalies)} anomaly signals detected in recent usage/spend.*",
                },
            },
            {"type": "divider"},
        ]
        for anomaly in anomalies[:3]:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{anomaly.get('type')}*\n"
                        f"{anomaly.get('message')}\n"
                        f"Severity: {anomaly.get('severity', 'unknown')}"
                    ),
                },
            })
        if len(anomalies) > 3:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"_+{len(anomalies) - 3} more anomalies_"}],
            })
        return blocks
    
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

    def _create_weekly_report_blocks(
        self,
        team_name: str,
        start_date: str,
        end_date: str,
        total_spend: float,
        potential_savings: float,
        savings_pct: float,
        idle_savings: float,
        anomaly_count: int,
        top_recommendations: List[Dict],
        provider_breakdown: List[Dict],
        dashboard_url: str,
    ) -> List[Dict]:
        """Create Slack blocks for weekly report."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Heliox Weekly Report",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{team_name}* · {start_date} to {end_date}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Spend (7 days):*\n{self._format_currency(total_spend)}"},
                    {"type": "mrkdwn", "text": f"*Potential savings:*\n{self._format_currency(potential_savings)}"},
                    {"type": "mrkdwn", "text": f"*Savings rate:*\n{savings_pct:.1f}%"},
                    {"type": "mrkdwn", "text": f"*Idle GPU waste:*\n{self._format_currency(idle_savings)}"},
                    {"type": "mrkdwn", "text": f"*Anomalies:*\n{anomaly_count}"},
                ],
            },
        ]
        if top_recommendations:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Top opportunities:*"},
            })
            for r in top_recommendations[:3]:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {r.get('title', '—')} — {self._format_currency(r.get('estimated_savings_usd', 0))}",
                    },
                })
        if provider_breakdown:
            provider_lines = ", ".join(
                f"{p.get('provider', '—')}: {self._format_currency(p.get('cost_usd', 0))}"
                for p in provider_breakdown[:3]
            )
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*By provider:* {provider_lines}"},
            })
        if dashboard_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View ROI Dashboard"},
                        "url": dashboard_url,
                    },
                ],
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

    async def send_anomaly_alert(self, anomalies: List[Dict]) -> bool:
        """Send anomaly detection alert."""
        logger.info(f"Sending anomaly alert: {len(anomalies)} anomalies")
        blocks = self._create_anomaly_alert_blocks(anomalies)
        text = f"Heliox Anomaly Alert: {len(anomalies)} signals detected"
        return await self._send_slack_message(blocks, text)

    async def send_weekly_report(
        self,
        team_name: str,
        start_date: str,
        end_date: str,
        total_spend: float,
        potential_savings: float,
        savings_pct: float,
        idle_savings: float,
        anomaly_count: int,
        top_recommendations: List[Dict],
        provider_breakdown: List[Dict],
        dashboard_url: str,
    ) -> bool:
        """Send weekly report to Slack."""
        logger.info("Sending weekly report")
        blocks = self._create_weekly_report_blocks(
            team_name=team_name,
            start_date=start_date,
            end_date=end_date,
            total_spend=total_spend,
            potential_savings=potential_savings,
            savings_pct=savings_pct,
            idle_savings=idle_savings,
            anomaly_count=anomaly_count,
            top_recommendations=top_recommendations,
            provider_breakdown=provider_breakdown,
            dashboard_url=dashboard_url,
        )
        text = f"Heliox Weekly Report: {self._format_currency(total_spend)} spend, {self._format_currency(potential_savings)} potential savings"
        return await self._send_slack_message(blocks, text)


def _get_team_alert_settings(db: Session, team_id: UUID) -> Optional[AlertSettings]:
    return db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()


def _get_team_slack_config(db: Session, team_id: UUID) -> tuple[Optional[str], float, bool]:
    from app.services.webhook_secrets import get_webhook_url

    settings_record = _get_team_alert_settings(db, team_id)
    if not settings_record or not settings_record.enable_slack:
        return None, float(BURN_RATE_THRESHOLD_USD), False
    webhook_url = get_webhook_url(db, team_id)
    threshold = float(settings_record.burn_rate_threshold_usd_per_day or BURN_RATE_THRESHOLD_USD)
    return webhook_url, threshold, bool(webhook_url)


def _get_team_email_config(db: Session, team_id: UUID) -> tuple[list[str], bool]:
    """Return (recipients_list, enabled) for email alerts."""
    from app.services.email_notifications import _recipients_list, is_email_enabled

    settings_record = _get_team_alert_settings(db, team_id)
    if (
        not settings_record
        or not settings_record.enable_email
        or not settings_record.email_recipients
        or not is_email_enabled()
    ):
        return [], False
    recipients = _recipients_list(settings_record.email_recipients)
    return recipients, bool(recipients)


async def check_and_send_burn_rate_alert(db: Session, team_id: UUID, date_str: Optional[str] = None) -> bool:
    """Check if burn rate exceeds threshold and send alert for a team (Slack + email)."""
    from datetime import date, timedelta
    from app.services.email_notifications import send_burn_rate_alert_email

    webhook_url, threshold, slack_enabled = _get_team_slack_config(db, team_id)
    email_recipients, email_enabled = _get_team_email_config(db, team_id)
    if not slack_enabled and not email_enabled:
        return False

    if date_str is None:
        check_date = date.today() - timedelta(days=1)
        date_str = check_date.strftime("%Y-%m-%d")

    query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.team_id == team_id,
        CostSnapshot.date == date_str
    )
    result = db.execute(query).scalar_one_or_none()
    daily_cost = float(result) if result else 0.0

    logger.info(f"[{team_id}] Daily cost for {date_str}: ${daily_cost:.2f}")

    if daily_cost <= threshold:
        return False

    sent = False
    if slack_enabled and webhook_url:
        slack_service = SlackNotificationService(webhook_url=webhook_url)
        sent = await slack_service.send_burn_rate_alert(
            daily_cost,
            threshold,
            date_str
        )
    if email_enabled and email_recipients:
        email_ok = await send_burn_rate_alert_email(
            to_emails=email_recipients,
            daily_cost=daily_cost,
            threshold=threshold,
            date_str=date_str,
        )
        sent = sent or email_ok
    return sent


async def check_and_send_idle_spend_alert(db: Session, team_id: UUID) -> bool:
    """Check for high-severity idle spend recommendations for a team (Slack + email)."""
    from datetime import date, timedelta
    from app.services.email_notifications import send_idle_spend_alert_email

    webhook_url, _, slack_enabled = _get_team_slack_config(db, team_id)
    email_recipients, email_enabled = _get_team_email_config(db, team_id)
    if not slack_enabled and not email_enabled:
        return False

    end_date = date.today()
    start_date = end_date - timedelta(days=14)

    filters = RecommendationFilters(
        start_date=start_date,
        end_date=end_date,
        min_severity=RecommendationSeverity.HIGH,
        types=[RecommendationType.IDLE_GPU],
        team_id=team_id,
    )

    rec_engine = RecommendationEngine(db)
    response = rec_engine.generate_recommendations(filters)
    idle_recommendations = [rec.model_dump() for rec in response.recommendations]

    logger.info(f"[{team_id}] Found {len(idle_recommendations)} idle spend recommendations")

    if not idle_recommendations:
        return False

    sent = False
    if slack_enabled and webhook_url:
        slack_service = SlackNotificationService(webhook_url=webhook_url)
        sent = await slack_service.send_idle_spend_alert(idle_recommendations)
    if email_enabled and email_recipients:
        email_ok = await send_idle_spend_alert_email(
            to_emails=email_recipients,
            recommendations=idle_recommendations,
        )
        sent = sent or email_ok
    return sent


async def send_daily_summary_report(db: Session, team_id: UUID) -> bool:
    """Generate and send daily summary report for a team (Slack + email)."""
    from datetime import date, timedelta
    from sqlalchemy import desc
    from app.services.email_notifications import send_daily_summary_email

    webhook_url, _, slack_enabled = _get_team_slack_config(db, team_id)
    email_recipients, email_enabled = _get_team_email_config(db, team_id)
    if not slack_enabled and not email_enabled:
        return False

    today = date.today()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    yesterday_query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.team_id == team_id,
        CostSnapshot.date == yesterday
    )
    daily_cost = float(db.execute(yesterday_query).scalar_one_or_none() or 0)
    
    weekly_query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.team_id == team_id,
        CostSnapshot.date >= week_ago
    )
    weekly_cost = float(db.execute(weekly_query).scalar_one_or_none() or 0)
    
    monthly_query = select(func.sum(CostSnapshot.cost_usd)).where(
        CostSnapshot.team_id == team_id,
        CostSnapshot.date >= month_ago
    )
    monthly_cost = float(db.execute(monthly_query).scalar_one_or_none() or 0)
    
    top_gpu_query = select(
        CostSnapshot.provider,
        CostSnapshot.gpu_type,
        func.sum(CostSnapshot.cost_usd).label("cost")
    ).where(
        CostSnapshot.team_id == team_id,
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
    
    filters = RecommendationFilters(
        start_date=yesterday - timedelta(days=14),
        end_date=yesterday,
        min_severity=RecommendationSeverity.HIGH,
        team_id=team_id,
    )
    rec_engine = RecommendationEngine(db)
    response = rec_engine.generate_recommendations(filters)
    
    high_severity_count = len(response.recommendations)
    total_savings = sum(rec.estimated_savings_usd for rec in response.recommendations)

    sent = False
    if slack_enabled and webhook_url:
        slack_service = SlackNotificationService(webhook_url=webhook_url)
        sent = await slack_service.send_daily_summary(
            daily_cost,
            weekly_cost,
            monthly_cost,
            top_models,
            high_severity_count,
            total_savings
        )
    if email_enabled and email_recipients:
        email_ok = await send_daily_summary_email(
            to_emails=email_recipients,
            daily_cost=daily_cost,
            weekly_cost=weekly_cost,
            monthly_cost=monthly_cost,
            top_models=top_models,
            high_severity_count=high_severity_count,
            total_savings=total_savings,
        )
        sent = sent or email_ok
    return sent


async def send_weekly_report_report(db: Session, team_id: UUID) -> bool:
    """Generate and send weekly report for a team (Slack + email)."""
    from app.services.email_notifications import send_weekly_report_email
    from app.services.weekly_report import get_weekly_report_data

    webhook_url, _, slack_enabled = _get_team_slack_config(db, team_id)
    email_recipients, email_enabled = _get_team_email_config(db, team_id)
    if not slack_enabled and not email_enabled:
        return False

    report = get_weekly_report_data(db, team_id)
    if not report:
        return False

    start_str = report.start_date.isoformat()
    end_str = report.end_date.isoformat()

    sent = False
    if slack_enabled and webhook_url:
        slack_service = SlackNotificationService(webhook_url=webhook_url)
        sent = await slack_service.send_weekly_report(
            team_name=report.team_name,
            start_date=start_str,
            end_date=end_str,
            total_spend=report.total_spend_usd,
            potential_savings=report.estimated_potential_savings_usd,
            savings_pct=report.savings_percent_of_spend,
            idle_savings=report.idle_savings_usd,
            anomaly_count=report.anomaly_count,
            top_recommendations=report.top_recommendations,
            provider_breakdown=report.provider_breakdown,
            dashboard_url=report.dashboard_url,
        )
    if email_enabled and email_recipients:
        email_ok = await send_weekly_report_email(
            to_emails=email_recipients,
            team_name=report.team_name,
            start_date=start_str,
            end_date=end_str,
            total_spend_usd=report.total_spend_usd,
            estimated_potential_savings_usd=report.estimated_potential_savings_usd,
            savings_percent=report.savings_percent_of_spend,
            top_recommendations=report.top_recommendations,
            provider_breakdown=report.provider_breakdown,
            anomaly_count=report.anomaly_count,
            idle_savings_usd=report.idle_savings_usd,
            dashboard_url=report.dashboard_url,
        )
        sent = sent or email_ok
    return sent


async def check_and_send_anomaly_alert(db: Session, team_id: UUID) -> bool:
    """Check anomaly detection for a team and send alert if needed (Slack + email)."""
    from app.services.anomaly import AnomalyDetectionService
    from app.services.email_notifications import send_anomaly_alert_email

    webhook_url, _, slack_enabled = _get_team_slack_config(db, team_id)
    email_recipients, email_enabled = _get_team_email_config(db, team_id)
    if not slack_enabled and not email_enabled:
        return False

    service = AnomalyDetectionService(db)
    result = service.detect(team_id=team_id)
    if not result.anomalies:
        return False

    sent = False
    if slack_enabled and webhook_url:
        slack_service = SlackNotificationService(webhook_url=webhook_url)
        sent = await slack_service.send_anomaly_alert(result.anomalies)
    if email_enabled and email_recipients:
        email_ok = await send_anomaly_alert_email(
            to_emails=email_recipients,
            anomalies=result.anomalies,
        )
        sent = sent or email_ok

    # Publish SSE event for each anomaly (fire-and-forget — never blocks Slack/email)
    try:
        from app.core.events import EventType, HelioxEvent, publish_event_sync
        for anomaly in result.anomalies:
            publish_event_sync(
                str(team_id),
                HelioxEvent(
                    event_type=EventType.ANOMALY_DETECTED,
                    team_id=str(team_id),
                    payload={
                        "anomaly_type": anomaly.get("type", "unknown"),
                        "severity": anomaly.get("severity", "medium"),
                        "message": anomaly.get("message", ""),
                        "value": anomaly.get("value"),
                        "baseline_mean": anomaly.get("baseline_mean"),
                        "probability": anomaly.get("probability"),
                    },
                ),
            )
    except Exception:
        pass  # SSE publish never disrupts existing Slack/email flow

    return sent

