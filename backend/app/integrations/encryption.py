"""Encryption utilities for integration configuration."""
import json
import logging
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

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
    
    def rotate_key(self, old_encrypted: str, new_key: bytes) -> str:
        """
        Re-encrypt config with a new key (for key rotation).
        
        Args:
            old_encrypted: Config encrypted with old key
            new_key: New encryption key
            
        Returns:
            Config re-encrypted with new key
        """
        # Decrypt with old key
        config = self.decrypt_config(old_encrypted)
        
        # Encrypt with new key
        new_fernet = Fernet(new_key)
        config_json = json.dumps(config)
        new_encrypted_bytes = new_fernet.encrypt(config_json.encode())
        
        return new_encrypted_bytes.decode()


# Global encryption instance
_encryption: IntegrationEncryption = None


def get_encryption() -> IntegrationEncryption:
    """
    Get encryption instance (singleton).
    
    Returns:
        IntegrationEncryption instance
    """
    global _encryption
    if _encryption is None:
        _encryption = IntegrationEncryption()
    return _encryption
