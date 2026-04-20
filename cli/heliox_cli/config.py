"""Local configuration management for ~/.heliox/config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

_CONFIG_DIR = Path.home() / ".heliox"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_KEYRING_SERVICE = "heliox-cli"
_KEYRING_KEY = "api_key"
_DEFAULT_API_URL = "https://api.heliox.ai"


class HelioxConfig(BaseModel):
    api_url: str = Field(default=_DEFAULT_API_URL)
    team_id: str = Field(default="")
    email: str = Field(default="")
    team_name: str = Field(default="")
    default_output: str = Field(default="table")


def load_config() -> HelioxConfig:
    """Load config from ~/.heliox/config.json, returning defaults if absent."""
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text())
            return HelioxConfig(**data)
        except Exception:
            pass
    return HelioxConfig()


def save_config(config: HelioxConfig) -> None:
    """Persist config to ~/.heliox/config.json."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps(config.model_dump(), indent=2))
    _CONFIG_FILE.chmod(0o600)


def get_api_key() -> Optional[str]:
    """Read API key from keyring, falling back to HELIOX_API_KEY env var."""
    env_key = os.environ.get("HELIOX_API_KEY")
    if env_key:
        return env_key
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY)
    except Exception:
        return None


def save_api_key(key: str) -> None:
    """Store API key in the OS keyring (never written to disk)."""
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY, key)
    except Exception as exc:
        # Keyring unavailable — warn and fall back to file-based storage
        import warnings
        warnings.warn(
            f"keyring unavailable ({exc}); storing API key in config file (less secure).",
            stacklevel=2,
        )
        cfg = load_config()
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fallback = _CONFIG_DIR / ".credentials"
        fallback.write_text(key)
        fallback.chmod(0o600)


def delete_api_key() -> None:
    """Remove API key from keyring and fallback file."""
    try:
        import keyring
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_KEY)
    except Exception:
        pass
    fallback = _CONFIG_DIR / ".credentials"
    if fallback.exists():
        fallback.unlink()


def get_api_url() -> str:
    """Return API URL: HELIOX_API_URL env var > config file > default."""
    env_url = os.environ.get("HELIOX_API_URL")
    if env_url:
        return env_url.rstrip("/")
    return load_config().api_url.rstrip("/")
