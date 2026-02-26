"""Cookie-based authentication and token blacklist."""
import hashlib
import logging
import time
from typing import Optional

from fastapi import Request
from jose import jwt

from app.core.config import get_settings
from app.core.cache import get_redis
from app.auth.security import SECRET_KEY, ALGORITHM

settings = get_settings()
logger = logging.getLogger(__name__)

BLACKLIST_PREFIX = "heliox:token_blacklist:"
TOKEN_TTL_BUFFER = 60  # seconds buffer for blacklist TTL


def get_token_from_cookie_or_header(request: Request) -> Optional[str]:
    """
    Extract JWT from cookie (preferred) or Authorization header.
    """
    # 1. Try cookie first
    cookie_name = settings.AUTH_COOKIE_NAME
    token = request.cookies.get(cookie_name)
    if token:
        return token

    # 2. Try Authorization: Bearer header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    return None


def is_token_blacklisted(token: str) -> bool:
    """Check if token is in Redis blacklist."""
    redis_client = get_redis()
    if not redis_client:
        return False
    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        key = f"{BLACKLIST_PREFIX}{token_hash}"
        return redis_client.exists(key) > 0
    except Exception as e:
        logger.warning(f"Redis blacklist check failed: {e}")
        return False


def blacklist_token(token: str) -> None:
    """Add token to Redis blacklist until it expires."""
    redis_client = get_redis()
    if not redis_client:
        logger.warning("Redis not available - cannot blacklist token")
        return
    try:
        # OWASP: Strict JWT validation - HS256 only, require exp
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        key = f"{BLACKLIST_PREFIX}{token_hash}"
        exp = payload.get("exp")
        if exp:
            ttl = int(exp) - int(time.time()) + TOKEN_TTL_BUFFER
            if ttl > 0:
                redis_client.setex(key, ttl, "1")
        else:
            redis_client.set(key, "1", ex=settings.AUTH_COOKIE_MAX_AGE)
    except Exception as e:
        logger.warning(f"Failed to blacklist token: {e}")
