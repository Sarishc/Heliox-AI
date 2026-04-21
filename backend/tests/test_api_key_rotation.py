"""Tests for API key rotation."""

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
