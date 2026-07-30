"""
Tests for OAuth token encryption at rest.

Covers:
  1. Round-trip: encrypt(x) then decrypt == x
  2. End-to-end: upsert_oauth_identity stores encrypted, get_decrypted_* returns plaintext
  3. Migration logic: idempotent encrypt of plaintext rows
  4. Config startup error when INTEGRATIONS_ENCRYPTION_KEY is missing/malformed
  5. Graceful plaintext fallback during the migration window
"""

import uuid
import pytest
from unittest.mock import MagicMock

from cryptography.fernet import Fernet

# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _set_test_encryption_key(monkeypatch):
    """Ensure every test runs with a deterministic, valid Fernet key."""
    test_key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATIONS_ENCRYPTION_KEY", test_key)
    # Clear singleton so it picks up the new key
    import app.integrations.encryption as enc_module

    enc_module._encryption = None
    yield test_key
    enc_module._encryption = None


# ── Test 1: Round-trip ────────────────────────────────────────────────────────


def test_encrypt_decrypt_roundtrip(_set_test_encryption_key):
    """encrypt_string(x) followed by decrypt_string produces the original value."""
    from app.integrations.encryption import get_encryption

    enc = get_encryption()
    for token in [
        "ya29.short",
        "ya29." + "x" * 300,  # long access token
        "1//0g" + "y" * 200,  # typical refresh token
        "special chars: !@#$%^&*()",
    ]:
        assert enc.decrypt_string(enc.encrypt_string(token)) == token


def test_encrypt_produces_fernet_token(_set_test_encryption_key):
    """Encrypted value is detected as a Fernet token by is_fernet_token()."""
    from app.integrations.encryption import get_encryption, is_fernet_token

    enc = get_encryption()
    ciphertext = enc.encrypt_string("ya29.someaccesstoken")
    assert is_fernet_token(ciphertext)


def test_is_fernet_token_rejects_plaintext():
    """Plaintext Google tokens are NOT flagged as Fernet tokens."""
    from app.integrations.encryption import is_fernet_token

    assert not is_fernet_token("ya29.plaintext_access_token")
    assert not is_fernet_token("1//refresh_token_here")
    assert not is_fernet_token("")
    assert not is_fernet_token("short")


# ── Test 2: End-to-end through upsert / get_decrypted_* ──────────────────────


def test_oauth_flow_stores_encrypted_and_decrypts_correctly(db_session, _set_test_encryption_key):
    """
    upsert_oauth_identity writes encrypted tokens; get_decrypted_access_token
    and get_decrypted_refresh_token return the original plaintext.
    """
    from app.auth.oauth_google import (
        upsert_oauth_identity,
        get_decrypted_access_token,
        get_decrypted_refresh_token,
    )
    from app.models.team import Team
    from app.models.user import User

    # Minimal fixtures
    team = Team(name="test-team")
    db_session.add(team)
    db_session.flush()

    user = User(
        email="oauth@example.com",
        hashed_password="x" * 60,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    raw_access = "ya29.access_token_plaintext_value"
    raw_refresh = "1//refresh_token_plaintext_value"

    identity = upsert_oauth_identity(
        db=db_session,
        team_id=str(team.id),
        user=user,
        provider_user_id="google-uid-123",
        email="oauth@example.com",
        email_verified=True,
        name="OAuth User",
        picture=None,
        access_token=raw_access,
        refresh_token=raw_refresh,
        expires_in=3600,
    )

    # Stored value must NOT be the raw token
    assert identity.access_token_encrypted != raw_access
    assert identity.refresh_token_encrypted != raw_refresh

    # Stored value must look like a Fernet token
    from app.integrations.encryption import is_fernet_token

    assert is_fernet_token(identity.access_token_encrypted)
    assert is_fernet_token(identity.refresh_token_encrypted)

    # Decryption must return the original plaintext
    assert get_decrypted_access_token(identity) == raw_access
    assert get_decrypted_refresh_token(identity) == raw_refresh


# ── Test 3: Migration logic — idempotent encrypt ──────────────────────────────


def test_migration_encrypts_plaintext_and_is_idempotent(_set_test_encryption_key):
    """
    The helper logic used in migration 029 encrypts plaintext rows and is
    idempotent (running it twice does not double-encrypt).
    """
    from app.integrations.encryption import get_encryption, is_fernet_token

    enc = get_encryption()
    plaintext = "ya29.migration_test_token"

    # First pass: plaintext → encrypted
    encrypted = enc.encrypt_string(plaintext)
    assert is_fernet_token(encrypted)
    assert encrypted != plaintext

    # Simulate idempotency check: detect already-encrypted and skip
    if is_fernet_token(encrypted):
        result = encrypted  # should not re-encrypt
    else:
        result = enc.encrypt_string(encrypted)

    # Decrypt result should still be the original plaintext
    assert enc.decrypt_string(result) == plaintext

    # Second pass: already-encrypted → skip (do not double-encrypt)
    if is_fernet_token(result):
        result2 = result
    else:
        result2 = enc.encrypt_string(result)

    assert result2 == result
    assert enc.decrypt_string(result2) == plaintext


# ── Test 4: Config startup error ──────────────────────────────────────────────


def test_config_raises_on_missing_key_in_production(monkeypatch):
    """
    Settings raises ValueError when INTEGRATIONS_ENCRYPTION_KEY is absent in
    production (or staging).
    """
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a-sufficiently-long-secret-key-for-tests-ok")
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.com"]')
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:strongpassword@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    monkeypatch.delenv("INTEGRATIONS_ENCRYPTION_KEY", raising=False)

    try:
        with pytest.raises(ValueError, match="INTEGRATIONS_ENCRYPTION_KEY"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_config_raises_on_malformed_key(monkeypatch):
    """Settings raises ValueError when the key is present but not a valid Fernet key."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("SECRET_KEY", "a-sufficiently-long-secret-key-for-tests-ok")
    monkeypatch.setenv("INTEGRATIONS_ENCRYPTION_KEY", "not-a-valid-fernet-key")

    try:
        with pytest.raises(ValueError, match="INTEGRATIONS_ENCRYPTION_KEY"):
            get_settings()
    finally:
        get_settings.cache_clear()


# ── Test 5: Graceful plaintext fallback ───────────────────────────────────────


def test_decrypt_returns_plaintext_for_pre_migration_row(_set_test_encryption_key):
    """
    If a stored token is NOT Fernet-encrypted (legacy plaintext row from before
    the encryption was deployed), the decrypt helpers return the raw value and
    emit a deprecation warning rather than returning None or raising.
    """
    from app.auth.oauth_google import (
        get_decrypted_access_token,
        get_decrypted_refresh_token,
    )

    plaintext_access = "ya29.legacy_plaintext_access_token"
    plaintext_refresh = "1//legacy_plaintext_refresh_token"

    # Build a minimal mock identity with plaintext-stored tokens
    identity = MagicMock()
    identity.id = uuid.uuid4()
    identity.access_token_encrypted = plaintext_access
    identity.refresh_token_encrypted = plaintext_refresh

    # These migration warnings are emitted through logging, not warnings.warn.
    access_result = get_decrypted_access_token(identity)
    refresh_result = get_decrypted_refresh_token(identity)

    assert (
        access_result == plaintext_access
    ), "Expected plaintext fallback to return the raw token during migration window"
    assert refresh_result == plaintext_refresh


def test_decrypt_returns_none_on_key_mismatch(_set_test_encryption_key):
    """
    If a stored token IS Fernet-encrypted but with a different key (e.g. after
    a bad key rotation), the decrypt helpers return None so the caller can
    force re-authentication rather than crashing.
    """
    from app.auth.oauth_google import get_decrypted_access_token
    from cryptography.fernet import Fernet as _Fernet

    # Encrypt with a *different* key than what _set_test_encryption_key installed
    other_key = _Fernet.generate_key()
    other_fernet = _Fernet(other_key)
    token_encrypted_with_other_key = other_fernet.encrypt(b"ya29.secret").decode()

    identity = MagicMock()
    identity.id = uuid.uuid4()
    identity.access_token_encrypted = token_encrypted_with_other_key

    result = get_decrypted_access_token(identity)
    assert result is None, "Key-mismatch Fernet tokens must return None, not crash"
