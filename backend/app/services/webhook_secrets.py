"""
Slack webhook encryption at rest.

Centralizes encrypt/decrypt for webhook URLs stored in alert_settings.
Uses INTEGRATIONS_ENCRYPTION_KEY (same as integration configs).
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.encryption import get_encryption
from app.models.alert_settings import AlertSettings


def mask_webhook(url: Optional[str]) -> Optional[str]:
    """Mask webhook URL for safe display (last 8 chars only)."""
    if not url:
        return None
    return f"***{url[-8:]}"


def get_webhook_url(db: Session, team_id: UUID) -> Optional[str]:
    """
    Get decrypted webhook URL for a team. Returns None if not configured.
    Only call when needed for outbound Slack send.
    """
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()
    if not settings or not settings.slack_webhook_encrypted:
        return None
    if not settings.enable_slack:
        return None
    try:
        return get_encryption().decrypt_string(settings.slack_webhook_encrypted)
    except ValueError:
        return None


def is_webhook_configured(db: Session, team_id: UUID) -> bool:
    """Check if webhook is configured without decrypting."""
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()
    return bool(settings and settings.slack_webhook_encrypted and settings.enable_slack)


def set_webhook_url(db: Session, team_id: UUID, webhook_url: Optional[str]) -> None:
    """
    Encrypt and store webhook URL. Pass None to clear.
    """
    settings = db.query(AlertSettings).filter(AlertSettings.team_id == team_id).first()
    if not settings:
        settings = AlertSettings(team_id=team_id)
        db.add(settings)
    if webhook_url:
        settings.slack_webhook_encrypted = get_encryption().encrypt_string(webhook_url)
        settings.enable_slack = True
    else:
        settings.slack_webhook_encrypted = None
        settings.enable_slack = False
    db.commit()
