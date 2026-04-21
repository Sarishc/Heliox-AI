"""Feature flags for gradual rollouts and enterprise controls."""

from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def get_feature_flags() -> dict[str, bool]:
    """
    Load feature flags from config.
    Uses FEATURE_FLAGS env: JSON object or comma-separated key=value.
    Example: FEATURE_FLAGS='{"integrations": true, "forecasting": true}'
    Or: FEATURE_FLAGS=integrations=true,forecasting=true
    """
    settings = get_settings()
    raw = getattr(settings, "FEATURE_FLAGS", None) or ""
    if not raw:
        return _default_flags()
    if isinstance(raw, dict):
        return {k: bool(v) for k, v in raw.items()}
    if isinstance(raw, str):
        if raw.strip().startswith("{"):
            import json

            try:
                return {k: bool(v) for k, v in json.loads(raw).items()}
            except Exception:
                return _default_flags()
        # Parse key=value,key2=value2
        result = {}
        for part in raw.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip().lower() in ("true", "1", "yes")
        return result if result else _default_flags()
    return _default_flags()


def _default_flags() -> dict[str, bool]:
    """Default flags (all on for backward compatibility)."""
    return {
        "integrations": True,
        "forecasting": True,
        "recommendations": True,
        "reports": True,
        "budgets": True,
        "anomalies": True,
        "api_key_rotation": True,
        "usage_analytics": True,
    }


def is_enabled(flag: str) -> bool:
    """Check if a feature flag is enabled."""
    return get_feature_flags().get(flag, True)


def get_all_flags() -> dict[str, bool]:
    """Return all feature flags (for admin/dashboard)."""
    return get_feature_flags().copy()
