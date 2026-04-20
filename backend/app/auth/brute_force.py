"""
OWASP: Brute force protection for login.

- 5 login attempts per minute per IP
- Account lockout after 5 failed attempts (15 min unlock)
- CAPTCHA required after 3 failures
- Brute force detection alerts

Redis is required. These functions raise HTTP 503 if Redis is unavailable.
Failing open (allowing unlimited login attempts) is not acceptable.
"""
import hashlib
import logging
import time
from typing import Optional

from app.core.cache import require_redis

logger = logging.getLogger(__name__)

LOGIN_ATTEMPTS_PREFIX = "heliox:login_attempts:"
LOGIN_LOCKOUT_PREFIX = "heliox:login_lockout:"
LOGIN_CAPTCHA_PREFIX = "heliox:login_captcha:"
LOGIN_RATE_PREFIX = "heliox:login_rate:"

LOGIN_RATE_LIMIT = 5  # attempts per minute per IP
LOGIN_LOCKOUT_AFTER = 5  # failed attempts
LOGIN_LOCKOUT_SECONDS = 15 * 60  # 15 minutes
LOGIN_CAPTCHA_AFTER = 3  # failures before CAPTCHA required
LOGIN_RATE_WINDOW = 60  # seconds


def _client_key(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest()[:32]


def _get_client_ip(request) -> str:
    headers = getattr(request, "headers", None) or {}
    forwarded = headers.get("X-Forwarded-For") if hasattr(headers, "get") else None
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else "unknown"


def check_login_rate_limit(client_ip: str) -> tuple[bool, int]:
    """
    Check if IP has exceeded 5 login attempts per minute.
    Returns (is_limited, retry_after_seconds).
    Raises HTTP 503 if Redis is unavailable.
    """
    redis_client = require_redis()
    key = f"{LOGIN_RATE_PREFIX}{_client_key(client_ip)}"
    now = int(time.time())
    window_start = now - (now % LOGIN_RATE_WINDOW)

    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, LOGIN_RATE_WINDOW * 2)
    if count > LOGIN_RATE_LIMIT:
        retry = window_start + LOGIN_RATE_WINDOW - now
        return True, max(1, retry)
    return False, LOGIN_RATE_WINDOW


def record_login_attempt(client_ip: str, email: str, success: bool) -> tuple[bool, bool, int]:
    """
    Record login attempt. Returns (is_locked_out, captcha_required, lockout_remaining_seconds).
    Raises HTTP 503 if Redis is unavailable.
    """
    redis_client = require_redis()

    ip_key = f"{LOGIN_ATTEMPTS_PREFIX}ip:{_client_key(client_ip)}"
    email_key = f"{LOGIN_ATTEMPTS_PREFIX}email:{hashlib.sha256(email.lower().encode()).hexdigest()[:24]}"

    if success:
        redis_client.delete(ip_key)
        redis_client.delete(email_key)
        return False, False, 0

    pipe = redis_client.pipeline()
    pipe.incr(ip_key)
    pipe.incr(email_key)
    pipe.expire(ip_key, LOGIN_LOCKOUT_SECONDS)
    pipe.expire(email_key, LOGIN_LOCKOUT_SECONDS)
    results = pipe.execute()
    ip_count = results[0]
    email_count = results[1]

    if ip_count >= LOGIN_LOCKOUT_AFTER or email_count >= LOGIN_LOCKOUT_AFTER:
        lock_key = f"{LOGIN_LOCKOUT_PREFIX}{_client_key(client_ip)}"
        redis_client.setex(lock_key, LOGIN_LOCKOUT_SECONDS, "1")
        _alert_brute_force(client_ip, email, ip_count, email_count)
        return True, True, LOGIN_LOCKOUT_SECONDS

    captcha_required = ip_count >= LOGIN_CAPTCHA_AFTER or email_count >= LOGIN_CAPTCHA_AFTER
    if captcha_required:
        captcha_key = f"{LOGIN_CAPTCHA_PREFIX}{_client_key(client_ip)}"
        redis_client.setex(captcha_key, LOGIN_RATE_WINDOW * 5, "1")

    return False, captcha_required, 0


def is_locked_out(client_ip: str) -> tuple[bool, int]:
    """
    Check if IP is locked out. Returns (is_locked, remaining_seconds).
    Raises HTTP 503 if Redis is unavailable.
    """
    redis_client = require_redis()
    key = f"{LOGIN_LOCKOUT_PREFIX}{_client_key(client_ip)}"
    ttl = redis_client.ttl(key)
    if ttl > 0:
        return True, ttl
    return False, 0


def is_captcha_required(client_ip: str) -> bool:
    """
    Check if CAPTCHA is required for this IP.
    Raises HTTP 503 if Redis is unavailable.
    """
    redis_client = require_redis()
    key = f"{LOGIN_CAPTCHA_PREFIX}{_client_key(client_ip)}"
    return redis_client.exists(key) > 0


def clear_captcha_requirement(client_ip: str, captcha_token: str) -> bool:
    """
    Clear CAPTCHA requirement only after successful server-side verification.
    Verifies token via hCaptcha siteverify API; clears Redis only if success.
    Raises HTTP 503 if Redis is unavailable.
    """
    from app.auth.captcha_verify import verify_captcha_token

    if not captcha_token or not captcha_token.strip():
        return False

    if not verify_captcha_token(captcha_token.strip(), remote_ip=client_ip):
        return False

    redis_client = require_redis()
    key = f"{LOGIN_CAPTCHA_PREFIX}{_client_key(client_ip)}"
    redis_client.delete(key)
    return True


def _alert_brute_force(client_ip: str, email: str, ip_count: int, email_count: int) -> None:
    """Log brute force lockout for alerting."""
    logger.warning(
        "Brute force lockout triggered",
        extra={
            "client_ip": client_ip,
            "email_hash": hashlib.sha256(email.lower().encode()).hexdigest()[:12],
            "ip_attempts": ip_count,
            "email_attempts": email_count,
        },
    )
