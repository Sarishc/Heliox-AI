"""Email notification service for Heliox alerts via Resend."""

import logging
from datetime import date
from typing import List, Optional

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _format_currency(amount: float) -> str:
    return f"${amount:,.2f}"


def _recipients_list(recipients_str: Optional[str]) -> List[str]:
    """Parse comma-separated recipients, dedupe, and normalize."""
    if not recipients_str or not recipients_str.strip():
        return []
    seen = set()
    result = []
    for email in recipients_str.split(","):
        email = email.strip().lower()
        if email and "@" in email and email not in seen:
            seen.add(email)
            result.append(email)
    return result


def is_email_enabled() -> bool:
    """Check if email sending is configured (Resend API key present)."""
    return bool(settings.RESEND_API_KEY)


def is_email_configured() -> bool:
    """
    Return True if transactional email delivery is configured.

    Use this to decide whether to block an action (e.g. forgot-password)
    that *requires* email delivery to complete meaningfully.
    """
    return bool(settings.RESEND_API_KEY)


async def send_email_alert(
    *,
    to_emails: List[str],
    subject: str,
    html_body: str,
) -> bool:
    """
    Send an alert email to recipients via Resend.

    Args:
        to_emails: List of recipient email addresses.
        subject: Email subject.
        html_body: HTML body content.

    Returns:
        True if sent successfully, False otherwise.
    """
    if not is_email_enabled():
        logger.info("Email notifications skipped: RESEND_API_KEY not configured")
        return False
    if not to_emails:
        logger.info("Email skipped: no recipients")
        return False

    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY

        params = {
            "from": settings.EMAIL_FROM,
            "to": to_emails,
            "subject": subject,
            "html": html_body,
        }
        r = resend.Emails.send(params)
        if r and getattr(r, "id", None):
            logger.info(f"Email alert sent successfully to {len(to_emails)} recipient(s), id={r.id}")
            return True
        logger.warning("Resend returned no email id")
        return False
    except Exception as e:
        logger.warning(
            f"Email alert failed: {type(e).__name__}: {e}",
            exc_info=True,
            extra={"service": "resend"},
        )
        return False


async def send_password_reset_email(*, to_email: str, reset_url: str, expires_minutes: int = 60) -> bool:
    """Send a password reset link to the user."""
    html_body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px 24px;">
  <h2 style="color: #1e293b; margin-bottom: 8px;">Reset your password</h2>
  <p style="color: #64748b; font-size: 14px; margin-bottom: 24px;">
    You requested a password reset for your Heliox AI account. Click the button below to choose a new password.
    This link expires in <strong>{expires_minutes} minutes</strong>.
  </p>
  <a href="{reset_url}"
     style="display: inline-block; background: #2563eb; color: #fff; text-decoration: none;
            font-size: 14px; font-weight: 600; padding: 12px 24px; border-radius: 8px;">
    Reset password
  </a>
  <p style="color: #94a3b8; font-size: 12px; margin-top: 32px;">
    If you didn't request this, you can safely ignore this email — your password will not change.<br/>
    For security, this link can only be used once.
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="color: #cbd5e1; font-size: 11px;">Heliox AI &bull; GPU Cost Optimization Platform</p>
</div>
"""
    return await send_email_alert(
        to_emails=[to_email],
        subject="Reset your Heliox AI password",
        html_body=html_body,
    )


async def send_email_verification(*, to_email: str, verify_url: str) -> bool:
    """Send an email verification link to a newly registered user."""
    html_body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 32px 24px;">
  <h2 style="color: #1e293b; margin-bottom: 8px;">Verify your email address</h2>
  <p style="color: #64748b; font-size: 14px; margin-bottom: 24px;">
    Welcome to Heliox AI! Please verify your email address to complete your account setup
    and unlock full access to your workspace.
  </p>
  <a href="{verify_url}"
     style="display: inline-block; background: #2563eb; color: #fff; text-decoration: none;
            font-size: 14px; font-weight: 600; padding: 12px 24px; border-radius: 8px;">
    Verify email address
  </a>
  <p style="color: #94a3b8; font-size: 12px; margin-top: 32px;">
    This link expires in 24 hours. If you didn't create a Heliox AI account you can safely ignore this email.
  </p>
  <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
  <p style="color: #cbd5e1; font-size: 11px;">Heliox AI &bull; GPU Cost Optimization Platform</p>
</div>
"""
    return await send_email_alert(
        to_emails=[to_email],
        subject="Verify your Heliox AI email address",
        html_body=html_body,
    )


def _html_header(title: str, emoji: str = "📢") -> str:
    return f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #333;">{emoji} {title}</h2>
  <p style="color: #666; font-size: 14px;">Heliox AI GPU Cost Optimization</p>
  <hr style="border: none; border-top: 1px solid #eee;" />
"""


def _html_footer() -> str:
    return """
  <p style="color: #888; font-size: 12px; margin-top: 24px;">
    This is an automated alert from Heliox AI. You can manage notification settings in your team alerts dashboard.
  </p>
</div>
"""


def _html_footer_with_link(dashboard_url: str) -> str:
    return f"""
  <p style="color: #888; font-size: 12px; margin-top: 24px;">
    <a href="{dashboard_url}" style="color: #2563eb;">View your ROI dashboard</a> • Manage alerts in settings.
  </p>
</div>
"""


async def send_weekly_report_email(
    *,
    to_emails: List[str],
    team_name: str,
    start_date: str,
    end_date: str,
    total_spend_usd: float,
    estimated_potential_savings_usd: float,
    savings_percent: float,
    top_recommendations: List[dict],
    provider_breakdown: List[dict],
    anomaly_count: int,
    idle_savings_usd: float,
    dashboard_url: str,
) -> bool:
    """Send weekly report email."""
    html = _html_header("Weekly GPU Cost Report", "📊")
    html += f"""
  <p>Hi — here's your <b>{team_name}</b> summary for <b>{start_date}</b> to <b>{end_date}</b>.</p>
  <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
    <tr><td style="padding: 8px 0;"><b>Total spend (7 days):</b></td><td>{_format_currency(total_spend_usd)}</td></tr>
    <tr><td style="padding: 8px 0;"><b>Estimated potential savings:</b></td><td style="color: #059669;">{_format_currency(estimated_potential_savings_usd)}</td></tr>
    <tr><td style="padding: 8px 0;"><b>Savings rate:</b></td><td>{savings_percent:.1f}% of spend</td></tr>
    <tr><td style="padding: 8px 0;"><b>Idle GPU waste identified:</b></td><td>{_format_currency(idle_savings_usd)}</td></tr>
    <tr><td style="padding: 8px 0;"><b>Anomalies detected:</b></td><td>{anomaly_count}</td></tr>
  </table>
  <p style="font-size: 12px; color: #666;">All savings are estimated potential. Actual savings depend on implementation.</p>
"""
    if top_recommendations:
        html += "  <p><b>Top opportunities:</b></p><ul>\n"
        for r in top_recommendations:
            html += f"    <li>{r.get('title', '—')} — {_format_currency(r.get('estimated_savings_usd', 0))}</li>\n"
        html += "  </ul>\n"
    if provider_breakdown:
        html += "  <p><b>Spend by provider:</b></p><ul>\n"
        for p in provider_breakdown[:5]:
            html += f"    <li>{p.get('provider', '—')}: {_format_currency(p.get('cost_usd', 0))} ({p.get('share_percent', 0):.1f}%)</li>\n"
        html += "  </ul>\n"
    html += _html_footer_with_link(dashboard_url)
    return await send_email_alert(
        to_emails=to_emails,
        subject=f"Heliox Weekly Report: {_format_currency(total_spend_usd)} spend · {_format_currency(estimated_potential_savings_usd)} potential savings",
        html_body=html,
    )


async def send_budget_alert_email(
    *,
    to_emails: List[str],
    env_label: str,
    project_label: str,
    budget: float,
    mtd_spend: float,
    percent_used: float,
    forecasted_eom: float,
    predicted_breach_date: Optional[date],
) -> bool:
    breach_text = predicted_breach_date.isoformat() if predicted_breach_date else "not projected"
    html = _html_header("Budget Guardrail Alert", "💰")
    html += f"""
  <table style="width: 100%; border-collapse: collapse;">
    <tr><td style="padding: 6px 0;"><b>Environment:</b></td><td>{env_label}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Project:</b></td><td>{project_label}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Budget:</b></td><td>{_format_currency(budget)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>MTD Spend:</b></td><td>{_format_currency(mtd_spend)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Used:</b></td><td>{percent_used * 100:.0f}%</td></tr>
    <tr><td style="padding: 6px 0;"><b>Forecast EOM:</b></td><td>{_format_currency(forecasted_eom)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Predicted breach:</b></td><td>{breach_text}</td></tr>
  </table>
"""
    html += _html_footer()
    return await send_email_alert(
        to_emails=to_emails,
        subject=f"Budget Alert: {percent_used * 100:.0f}% used ({env_label})",
        html_body=html,
    )


async def send_burn_rate_alert_email(
    *,
    to_emails: List[str],
    daily_cost: float,
    threshold: float,
    date_str: str,
) -> bool:
    over = daily_cost - threshold
    pct = (over / threshold) * 100 if threshold > 0 else 0
    html = _html_header("High Burn Rate Alert", "🔥")
    html += f"""
  <p>Daily GPU spending has exceeded the threshold.</p>
  <table style="width: 100%; border-collapse: collapse;">
    <tr><td style="padding: 6px 0;"><b>Date:</b></td><td>{date_str}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Daily Cost:</b></td><td>{_format_currency(daily_cost)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Threshold:</b></td><td>{_format_currency(threshold)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Over by:</b></td><td>{_format_currency(over)} ({pct:.1f}%)</td></tr>
  </table>
  <p style="color: #666;">Review your GPU usage in the Heliox dashboard to identify cost drivers.</p>
"""
    html += _html_footer()
    return await send_email_alert(
        to_emails=to_emails,
        subject=f"High Burn Rate Alert: {_format_currency(daily_cost)} on {date_str}",
        html_body=html,
    )


async def send_idle_spend_alert_email(
    *,
    to_emails: List[str],
    recommendations: List[dict],
) -> bool:
    total_savings = sum(r.get("estimated_savings_usd", 0) for r in recommendations)
    html = _html_header("Idle GPU Spend Detected", "⚠️")
    html += f"""
  <p>High-severity idle spend recommendations found.</p>
  <ul>
    <li><b>Total Potential Savings:</b> {_format_currency(total_savings)}/month</li>
    <li><b>Number of Issues:</b> {len(recommendations)}</li>
  </ul>
  <p><b>Top recommendations:</b></p>
  <ul>
"""
    for rec in recommendations[:5]:
        title = rec.get("title", "Recommendation")
        savings = rec.get("estimated_savings_usd", 0)
        html += f"    <li>{title} — Savings: {_format_currency(savings)}/month</li>\n"
    if len(recommendations) > 5:
        html += f"    <li><em>+{len(recommendations) - 5} more in dashboard</em></li>\n"
    html += "  </ul>\n"
    html += _html_footer()
    return await send_email_alert(
        to_emails=to_emails,
        subject=f"Idle GPU Spend Alert: {len(recommendations)} issues, {_format_currency(total_savings)} potential savings",
        html_body=html,
    )


async def send_daily_summary_email(
    *,
    to_emails: List[str],
    daily_cost: float,
    weekly_cost: float,
    monthly_cost: float,
    top_models: List[dict],
    high_severity_count: int,
    total_savings: float,
) -> bool:
    html = _html_header("Heliox Daily Summary", "📊")
    html += f"""
  <table style="width: 100%; border-collapse: collapse;">
    <tr><td style="padding: 6px 0;"><b>Yesterday:</b></td><td>{_format_currency(daily_cost)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Last 7 Days:</b></td><td>{_format_currency(weekly_cost)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Last 30 Days:</b></td><td>{_format_currency(monthly_cost)}</td></tr>
    <tr><td style="padding: 6px 0;"><b>Potential Savings:</b></td><td>{_format_currency(total_savings)}/mo</td></tr>
  </table>
"""
    if top_models:
        html += "  <p><b>Top GPU Consumers (Yesterday):</b></p><ul>\n"
        for m in top_models[:5]:
            html += f"    <li>{m.get('model_name', 'Unknown')}: {_format_currency(m.get('cost', 0))}</li>\n"
        html += "  </ul>\n"
    if high_severity_count > 0:
        html += f"""
  <p style="color: #c0392b;">⚠️ <b>{high_severity_count} high-severity recommendations</b> available. Review them in your Heliox dashboard.</p>
"""
    html += _html_footer()
    return await send_email_alert(
        to_emails=to_emails,
        subject=f"Heliox Daily Summary: {_format_currency(daily_cost)} spent yesterday",
        html_body=html,
    )


async def send_anomaly_alert_email(
    *,
    to_emails: List[str],
    anomalies: List[dict],
) -> bool:
    html = _html_header("Anomaly Detected", "🚨")
    html += f"""
  <p><b>{len(anomalies)} anomaly signals</b> detected in recent usage/spend.</p>
  <ul>
"""
    for a in anomalies[:5]:
        atype = a.get("type", "unknown")
        msg = a.get("message", "")
        sev = a.get("severity", "unknown")
        html += f"    <li><b>{atype}</b>: {msg} (Severity: {sev})</li>\n"
    if len(anomalies) > 5:
        html += f"    <li><em>+{len(anomalies) - 5} more</em></li>\n"
    html += "  </ul>\n"
    html += _html_footer()
    return await send_email_alert(
        to_emails=to_emails,
        subject=f"Heliox Anomaly Alert: {len(anomalies)} signals detected",
        html_body=html,
    )
