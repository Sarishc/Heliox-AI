"""
Session JWTs: the app signs HS256 tokens and accepts nothing else.

Guards the PyJWT upgrade: valid tokens round-trip, while expired, tampered,
unsigned ("alg": "none"), other-algorithm and wrong-key tokens are rejected.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.auth.security import create_access_token
from app.core.config import get_settings
from app.core.security import decode_access_token

SECRET = get_settings().SECRET_KEY


def _rejected(token: str) -> None:
    with pytest.raises(HTTPException) as exc:
        decode_access_token(token)
    assert exc.value.status_code == 401


def test_valid_session_token_round_trips():
    token = create_access_token(data={"sub": "user@example.com"})
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    assert decode_access_token(token)["sub"] == "user@example.com"


def test_expired_token_is_rejected():
    _rejected(create_access_token(data={"sub": "user@example.com"}, expires_delta=timedelta(seconds=-5)))


def test_tampered_signature_is_rejected():
    header, payload, signature = create_access_token(data={"sub": "user@example.com"}).split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
    _rejected(f"{header}.{payload}.{flipped}")


def test_unsigned_token_is_rejected():
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    _rejected(jwt.encode({"sub": "admin@example.com", "exp": exp}, key=None, algorithm="none"))


def test_other_hmac_algorithm_with_the_right_secret_is_rejected():
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    _rejected(jwt.encode({"sub": "user@example.com", "exp": exp}, SECRET, algorithm="HS512"))


def test_token_signed_with_another_secret_is_rejected():
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    _rejected(jwt.encode({"sub": "user@example.com", "exp": exp}, "x" * 64, algorithm="HS256"))
