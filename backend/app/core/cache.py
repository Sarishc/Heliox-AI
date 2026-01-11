"""Redis cache utilities."""
import logging
from typing import Optional

import redis
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """
    Get Redis client instance.
    
    Returns None if Redis is not available or connection fails.
    This allows the application to work without Redis.
    """
    global _redis_client
    
    if _redis_client is None:
        try:
            # Parse Redis URL
            _redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            _redis_client.ping()
        except Exception as e:
            logger.warning(
                f"Redis connection failed: {type(e).__name__}",
                exc_info=True,
                extra={"error_type": type(e).__name__, "service": "redis"}
            )
            _redis_client = None
    
    return _redis_client

