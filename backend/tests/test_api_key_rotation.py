"""Tests for API key rotation."""

from datetime import datetime, timedelta, timezone

from app.models.team import Team
from app.models.team_api_key import TeamAPIKey


def test_api_key_rotation(db_session):
    team = Team(name="Key Team")
    db_session.add(team)
    db_session.commit()

    key1 = TeamAPIKey(
        team_id=team.id,
        key_name="primary",
        key_hash=TeamAPIKey.hash_key("key1"),
        is_active=True,
    )
    db_session.add(key1)
    db_session.commit()

    key1.is_active = False
    key2 = TeamAPIKey(
        team_id=team.id,
        key_name="rotated",
        key_hash=TeamAPIKey.hash_key("key2"),
        is_active=True,
    )
    db_session.add(key2)
    db_session.commit()

    assert key1.is_active is False
    assert key2.is_active is True


def test_expired_api_key_is_rejected():
    key = TeamAPIKey(
        key_name="expired",
        key_hash=TeamAPIKey.hash_key("expired-key"),
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert not key.verify_key("expired-key")


def test_unexpired_api_key_is_accepted():
    key = TeamAPIKey(
        key_name="valid",
        key_hash=TeamAPIKey.hash_key("valid-key"),
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert key.verify_key("valid-key")
