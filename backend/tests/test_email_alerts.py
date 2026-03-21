"""Tests for email alert functionality."""
import pytest
from uuid import uuid4

from app.schemas.alert_settings import (
    EmailAlertsRequest,
    _mask_email_recipients,
)


def test_mask_email_recipients():
    """Test masking of email recipients for safe display."""
    count, masked = _mask_email_recipients("a@x.com, b@y.com")
    assert count == 2
    assert "a***@x.com" in masked or "***@x.com" in masked
    assert "b***@y.com" in masked or "***@y.com" in masked

    count, masked = _mask_email_recipients(None)
    assert count == 0
    assert masked is None

    count, masked = _mask_email_recipients("")
    assert count == 0
    assert masked is None

    count, masked = _mask_email_recipients("invalid")
    assert count == 0
    assert masked is None


def test_email_alerts_request_validation():
    """Test EmailAlertsRequest validation."""
    team_id = uuid4()
    # Valid: enable_email with recipients
    req = EmailAlertsRequest(
        team_id=team_id,
        enable_email=True,
        email_recipients="alerts@example.com, finance@example.com",
    )
    assert req.enable_email is True
    assert "alerts@example.com" in req.email_recipients or "finance@example.com" in req.email_recipients

    # Invalid: enable_email without recipients
    with pytest.raises(ValueError, match="At least one email"):
        EmailAlertsRequest(
            team_id=team_id,
            enable_email=True,
            email_recipients="",
        )

    with pytest.raises(ValueError, match="At least one email"):
        EmailAlertsRequest(
            team_id=team_id,
            enable_email=True,
            email_recipients=None,
        )

    # Invalid email format
    with pytest.raises(ValueError, match="Invalid email"):
        EmailAlertsRequest(
            team_id=team_id,
            enable_email=True,
            email_recipients="notanemail",
        )


def test_email_recipients_dedup_logic():
    """Test duplicate recipient normalization logic (mirrors API behavior)."""
    recipients = "Alerts@Example.com, finance@example.com , alerts@example.com"
    parsed = [e.strip().lower() for e in recipients.split(",") if e.strip() and "@" in e]
    seen = set()
    unique = []
    for e in parsed:
        if e not in seen:
            seen.add(e)
            unique.append(e)
    result = ", ".join(unique) if unique else None
    assert "alerts@example.com" in result
    assert "finance@example.com" in result
    assert len(unique) == 2
