"""Adversarial authentication checks added during the deep audit."""

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.auth.security import ALGORITHM, SECRET_KEY, get_password_hash
from app.core.config import get_settings
from app.crud.user import user as crud_user
from app.main import app
from app.models.user import User


def test_expired_session_token_is_rejected():
    """An otherwise valid JWT with an expired timestamp must return 401."""
    expired = jwt.encode(
        {
            "sub": "expired-session@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    response = TestClient(app).get(
        "/api/v1/teams/",
        cookies={get_settings().AUTH_COOKIE_NAME: expired},
    )

    assert response.status_code == 401


def test_password_reset_token_is_hashed_expiring_and_single_use(db_session):
    """Reset tokens are stored hashed, expire, and disappear after consumption."""
    user = User(
        email="reset-deep-audit@example.com",
        hashed_password=get_password_hash("BeforeReset123!"),
        full_name="Reset Deep Audit",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    raw_token = crud_user.create_password_reset_token(db_session, user=user)
    assert user.password_reset_token != raw_token
    expires_at = user.password_reset_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)
    assert crud_user.get_by_password_reset_token(db_session, raw_token=raw_token) == user

    crud_user.reset_password(db_session, user=user, new_password="AfterReset123!")

    assert user.password_reset_token is None
    assert user.password_reset_token_expires_at is None
    assert crud_user.get_by_password_reset_token(db_session, raw_token=raw_token) is None
