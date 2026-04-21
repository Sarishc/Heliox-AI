"""Redis cache utilities."""

import logging
from typing import Optional

import redis
from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """
    Get Redis client for optional caching uses (forecasting, assistant, etc.).

    Returns None if Redis is unreachable. Callers that use Redis only for
    caching (not security) can handle None gracefully.

    Security-critical callers (rate limiting, brute force, token blacklist)
    must use require_redis() instead.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            ssl_cert_reqs=None,  # ElastiCache TLS in VPC — cert pinning not required
        )
        _redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning(
            "Redis connection failed: %s",
            type(e).__name__,
            extra={"error_type": type(e).__name__, "service": "redis"},
        )
        # Do NOT cache None here — allows reconnect attempts on subsequent calls
        _redis_client = None

    return _redis_client


def require_redis() -> redis.Redis:
    """
    Get Redis client for security-critical uses.

    Raises HTTP 503 if Redis is unavailable.

    Failing open on security controls (rate limiting, brute-force protection,
    token blacklisting) is a security risk — a Redis outage must not silently
    disable these controls.
    """
    client = get_redis()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache service unavailable. Please try again shortly.",
        )
    return client
