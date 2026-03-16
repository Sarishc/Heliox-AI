"""Tests for Slack webhook encryption at rest."""
import pytest

from app.integrations.encryption import get_encryption
from app.models.alert_settings import AlertSettings
from app.models.team import Team
from app.services.webhook_secrets import (
    get_webhook_url,
    is_webhook_configured,
    mask_webhook,
    set_webhook_url,
)


@pytest.fixture
def sample_team(db_session):
    """Create a sample team."""
    team = Team(name="Webhook Test Team")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


def test_webhook_stored_encrypted_not_plaintext(db_session, sample_team):
    """Webhook URL must be encrypted in DB, never stored as plaintext."""
    url = "https://hooks.slack.com/services/T000/B000/secret123"
    set_webhook_url(db_session, sample_team.id, url)

    row = (
        db_session.query(AlertSettings)
        .filter(AlertSettings.team_id == sample_team.id)
        .first()
    )
    assert row is not None
    assert row.slack_webhook_encrypted is not None
    # Stored value must NOT be the plaintext URL
    assert url not in (row.slack_webhook_encrypted or "")
    # Encrypted value looks like Fernet base64 (starts with gAAAAA or similar)
    assert len(row.slack_webhook_encrypted) > 20
    assert row.slack_webhook_encrypted != url


def test_get_webhook_url_returns_decrypted(db_session, sample_team):
    """get_webhook_url returns the decrypted URL for outbound sends."""
    url = "https://hooks.slack.com/services/T111/B222/xyz789"
    set_webhook_url(db_session, sample_team.id, url)

    decrypted = get_webhook_url(db_session, sample_team.id)
    assert decrypted == url


def test_get_webhook_url_returns_none_when_not_configured(db_session, sample_team):
    """get_webhook_url returns None when no webhook is set."""
    assert get_webhook_url(db_session, sample_team.id) is None


def test_mask_webhook_never_exposes_full_url():
    """mask_webhook must never return the full URL."""
    url = "https://hooks.slack.com/services/T000/B000/abcd1234"
    masked = mask_webhook(url)
    assert masked == "***abcd1234"
    assert url not in (masked or "")
    assert "***" in (masked or "")


def test_mask_webhook_handles_none():
    """mask_webhook returns None for None input."""
    assert mask_webhook(None) is None


def test_set_webhook_url_clears_when_none(db_session, sample_team):
    """set_webhook_url with None clears the stored webhook."""
    set_webhook_url(db_session, sample_team.id, "https://hooks.slack.com/x")
    assert is_webhook_configured(db_session, sample_team.id)

    set_webhook_url(db_session, sample_team.id, None)
    assert not is_webhook_configured(db_session, sample_team.id)
    assert get_webhook_url(db_session, sample_team.id) is None

    row = (
        db_session.query(AlertSettings)
        .filter(AlertSettings.team_id == sample_team.id)
        .first()
    )
    assert row.slack_webhook_encrypted is None


def test_is_webhook_configured_without_decrypting(db_session, sample_team):
    """is_webhook_configured checks presence without decrypting."""
    assert not is_webhook_configured(db_session, sample_team.id)

    set_webhook_url(db_session, sample_team.id, "https://hooks.slack.com/y")
    assert is_webhook_configured(db_session, sample_team.id)


def test_update_webhook_overwrites(db_session, sample_team):
    """Updating webhook overwrites previous value."""
    set_webhook_url(db_session, sample_team.id, "https://hooks.slack.com/old")
    assert get_webhook_url(db_session, sample_team.id) == "https://hooks.slack.com/old"

    set_webhook_url(db_session, sample_team.id, "https://hooks.slack.com/new")
    assert get_webhook_url(db_session, sample_team.id) == "https://hooks.slack.com/new"


def test_delete_settings_removes_encrypted_value(db_session, sample_team):
    """Deleting alert settings removes the encrypted webhook."""
    set_webhook_url(db_session, sample_team.id, "https://hooks.slack.com/z")
    db_session.delete(
        db_session.query(AlertSettings)
        .filter(AlertSettings.team_id == sample_team.id)
        .first()
    )
    db_session.commit()

    # Row is gone; get_webhook_url returns None
    assert get_webhook_url(db_session, sample_team.id) is None


def test_response_masking_never_exposes_full_url(db_session, sample_team):
    """API response masking: full webhook URL must never appear in response."""
    url = "https://hooks.slack.com/services/team-a/secret"
    set_webhook_url(db_session, sample_team.id, url)

    # Simulate what _to_response does: mask_webhook(get_webhook_url(...))
    masked = mask_webhook(get_webhook_url(db_session, sample_team.id))
    assert "https://" not in (masked or "")
    assert "hooks.slack.com" not in (masked or "")
    assert "***" in (masked or "")
    assert len(masked or "") < len(url)
