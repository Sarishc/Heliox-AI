"""Encryption utilities for integration configuration and OAuth tokens."""

import base64
import json
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
settings = get_settings()


class IntegrationEncryption:
    """
    Handle encryption/decryption of integration configuration.

    Uses Fernet (symmetric encryption) to encrypt sensitive configuration
    data at rest. The encryption key is stored in environment variables.
    """

    def __init__(self):
        """Initialize encryption with key from settings."""
        # Get encryption key from environment
        key = getattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", None)

        if not key:
            # Generate a key for development (NEVER do this in production)
            if settings.ENV == "dev":
                logger.warning(
                    "INTEGRATIONS_ENCRYPTION_KEY not set. Generating temporary key for development. "
                    "Set INTEGRATIONS_ENCRYPTION_KEY in production!"
                )
                key = Fernet.generate_key().decode()
            else:
                raise ValueError(
                    "INTEGRATIONS_ENCRYPTION_KEY must be set in production. "
                    "Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )

        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()

        self.fernet = Fernet(key)

    def encrypt_config(self, config: Dict[str, Any]) -> str:
        """
        Encrypt configuration dictionary.

        Args:
            config: Configuration dictionary to encrypt

        Returns:
            Encrypted configuration as base64 string
        """
        # SECURITY: Never log the original config (contains secrets)
        logger.debug("Encrypting integration configuration")

        # Convert dict to JSON string
        config_json = json.dumps(config)

        # Encrypt
        encrypted_bytes = self.fernet.encrypt(config_json.encode())

        # Return as string
        return encrypted_bytes.decode()

    def decrypt_config(self, encrypted_config: str) -> Dict[str, Any]:
        """
        Decrypt configuration string.

        Args:
            encrypted_config: Encrypted configuration string

        Returns:
            Decrypted configuration dictionary

        Raises:
            ValueError: If decryption fails (invalid key or corrupted data)
        """
        logger.debug("Decrypting integration configuration")

        try:
            # Decrypt
            decrypted_bytes = self.fernet.decrypt(encrypted_config.encode())

            # Parse JSON
            config = json.loads(decrypted_bytes.decode())

            # SECURITY: Never log the decrypted config (contains secrets)
            return config

        except InvalidToken:
            logger.error("Failed to decrypt integration config: invalid token or key")
            raise ValueError(
                "Failed to decrypt integration configuration. "
                "The encryption key may have changed or the data is corrupted."
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse decrypted config as JSON: {e}")
            raise ValueError("Decrypted configuration is not valid JSON")

    def encrypt_string(self, value: str) -> str:
        """
        Encrypt a single string (e.g. webhook URL).

        Args:
            value: Plaintext string to encrypt

        Returns:
            Encrypted string (base64)
        """
        if not value:
            return ""
        encrypted_bytes = self.fernet.encrypt(value.encode())
        return encrypted_bytes.decode()

    def decrypt_string(self, encrypted: str) -> str:
        """
        Decrypt a single string.

        Args:
            encrypted: Encrypted string from encrypt_string

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If decryption fails
        """
        if not encrypted:
            return ""
        try:
            decrypted_bytes = self.fernet.decrypt(encrypted.encode())
            return decrypted_bytes.decode()
        except InvalidToken:
            raise ValueError("Failed to decrypt. The encryption key may have changed or the data is corrupted.")

    def rotate_key(self, old_encrypted: str, new_key: bytes) -> str:
        """Re-encrypt a JSON config blob with a new key."""
        config = self.decrypt_config(old_encrypted)
        new_fernet = Fernet(new_key)
        config_json = json.dumps(config)
        return new_fernet.encrypt(config_json.encode()).decode()

    def rotate_string(self, old_encrypted: str, new_fernet: Fernet) -> str:
        """
        Re-encrypt a single string token with a new Fernet key.

        Args:
            old_encrypted: String encrypted with the current key (self.fernet)
            new_fernet: Fernet instance initialised with the new key

        Returns:
            String re-encrypted with new_fernet
        """
        plaintext = self.decrypt_string(old_encrypted)
        return new_fernet.encrypt(plaintext.encode()).decode()


# Global encryption instance
_encryption: Optional[IntegrationEncryption] = None


def get_encryption() -> IntegrationEncryption:
    """Get the global encryption singleton."""
    global _encryption
    if _encryption is None:
        _encryption = IntegrationEncryption()
    return _encryption


def is_fernet_token(value: str) -> bool:
    """
    Return True if *value* looks like a Fernet-encrypted token.

    Fernet output is URL-safe base64; when decoded the first byte is always
    0x80 (the Fernet version byte).  The minimum encoded length of a Fernet
    token (empty plaintext, 1 AES block) is ~100 characters.
    """
    if not value or len(value) < 56:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode() + b"==")
        return len(decoded) >= 41 and decoded[0] == 0x80
    except Exception:
        return False


def rotate_encryption_key(old_key: str, new_key: str, db: "Session") -> Dict[str, int]:
    """
    Re-encrypt all OAuth tokens in the database from *old_key* to *new_key*.

    This is a pure-Python CLI helper — it does not use the global singleton so
    it can be called standalone without restarting the app.

    Args:
        old_key: Current Fernet key (base64url string)
        new_key: Replacement Fernet key (base64url string)
        db:      SQLAlchemy Session

    Returns:
        Dict with counts: {"rotated": int, "skipped": int, "errors": int}
    """
    import sqlalchemy as sa
    from app.models.oauth_identity import OAuthIdentity

    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key.encode())

    old_enc = IntegrationEncryption.__new__(IntegrationEncryption)
    old_enc.fernet = old_fernet

    rows = (
        db.query(OAuthIdentity)
        .filter(
            sa.or_(
                OAuthIdentity.access_token_encrypted.isnot(None),
                OAuthIdentity.refresh_token_encrypted.isnot(None),
            )
        )
        .all()
    )

    rotated = skipped = errors = 0

    for identity in rows:
        changed = False
        for attr in ("access_token_encrypted", "refresh_token_encrypted"):
            value = getattr(identity, attr)
            if not value:
                continue
            try:
                # Decrypt with old key, re-encrypt with new key
                re_encrypted = old_enc.rotate_string(value, new_fernet)
                setattr(identity, attr, re_encrypted)
                changed = True
            except Exception as exc:
                logger.error(
                    f"rotate_encryption_key: failed to rotate {attr} for " f"OAuthIdentity {identity.id}: {exc}"
                )
                errors += 1

        if changed:
            rotated += 1
        else:
            skipped += 1

    if rotated:
        db.commit()
        logger.info(f"rotate_encryption_key: rotated={rotated} skipped={skipped} errors={errors}")

    return {"rotated": rotated, "skipped": skipped, "errors": errors}
