"""Tests for Sentry configuration and safety."""
import os

import pytest

from app.core.observability import (
    _sentry_before_send,
    _should_enable_sentry,
    init_sentry,
    init_sentry_celery,
)


def test_sentry_disabled_when_dsn_empty(monkeypatch):
    """Sentry is disabled when SENTRY_DSN is empty."""
    monkeypatch.setattr("app.core.observability.settings.SENTRY_DSN", "")
    monkeypatch.setattr("app.core.observability.settings.ENV", "production")
    assert not _should_enable_sentry()


def test_sentry_disabled_in_test_env(monkeypatch):
    """Sentry is disabled when ENV=test."""
    monkeypatch.setattr("app.core.observability.settings.SENTRY_DSN", "https://key@sentry.io/1")
    monkeypatch.setattr("app.core.observability.settings.ENV", "test")
    assert not _should_enable_sentry()


def test_sentry_enabled_when_dsn_set_and_not_test(monkeypatch):
    """Sentry is enabled when DSN is set and ENV is not test."""
    monkeypatch.setattr("app.core.observability.settings.SENTRY_DSN", "https://key@sentry.io/1")
    monkeypatch.setattr("app.core.observability.settings.ENV", "production")
    assert _should_enable_sentry()


def test_before_send_scrubs_authorization_header():
    """before_send scrubs Authorization and X-API-Key headers."""
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token-123",
                "X-API-Key": "sk_live_abc123",
                "Content-Type": "application/json",
            }
        }
    }
    result = _sentry_before_send(event, {})
    assert result is not None
    assert result["request"]["headers"]["Authorization"] == "[Filtered]"
    assert result["request"]["headers"]["X-API-Key"] == "[Filtered]"
    assert result["request"]["headers"]["Content-Type"] == "application/json"


def test_before_send_scrubs_cookies():
    """before_send scrubs cookies."""
    event = {
        "request": {
            "cookies": "session=abc123; auth=xyz789"
        }
    }
    result = _sentry_before_send(event, {})
    assert result is not None
    assert result["request"]["cookies"] == "[Filtered]"


def test_before_send_scrubs_sensitive_extra_keys():
    """before_send scrubs sensitive keys from extra context."""
    event = {
        "extra": {
            "api_key": "sk_secret",
            "path": "/api/v1/teams",
        }
    }
    result = _sentry_before_send(event, {})
    assert result is not None
    assert result["extra"]["api_key"] == "[Filtered]"
    assert result["extra"]["path"] == "/api/v1/teams"


def test_init_sentry_no_op_when_disabled(monkeypatch):
    """init_sentry does not raise when DSN is empty."""
    monkeypatch.setattr("app.core.observability.settings.SENTRY_DSN", "")
    init_sentry()  # Should not raise


def test_init_sentry_no_op_in_test(monkeypatch):
    """init_sentry does not initialize when ENV=test."""
    monkeypatch.setattr("app.core.observability.settings.SENTRY_DSN", "https://x@sentry.io/1")
    monkeypatch.setattr("app.core.observability.settings.ENV", "test")
    init_sentry()  # Should not raise, should not init


def test_before_send_returns_event_for_valid_input():
    """before_send returns event (does not drop) for normal events."""
    event = {"message": "Test error", "level": "error"}
    result = _sentry_before_send(event, {})
    assert result is not None
    assert result["message"] == "Test error"
