"""
OWASP: Brute force protection for login.

Controls are keyed by the account being attacked and by the client, where the
client comes from app.core.client_ip (never from raw forwarding headers):

- 5 attempts/minute for one account from one client, 10/minute for one account
  from all clients, 30/minute per client (300/minute through a shared proxy
  that doesn't identify its clients)
- CAPTCHA after 3 failed attempts on the account, or 10 from one client
- Account lockout after 5 failed attempts (15 min), client lockout after 20.
  A lockout blocks the correct password too.
- The same responses for registered and unknown emails

A trusted proxy that doesn't forward client addresses ("shared") can't be
locked out or forced into CAPTCHA, since that would punish every user behind it.

Redis is required. These functions raise HTTP 503 if Redis is unavailable.
Failing open (allowing unlimited login attempts) is not acceptable.

Keys live under heliox:login:v2:*. Keys written by the previous scheme
(heliox:login_attempts:*, heliox:login_lockout:*, heliox:login_captcha:*,
heliox:login_rate:*) are no longer read and expire on their own TTLs (<= 15 min).
"""

import hashlib
import logging
import time
from typing import Union

from app.core.cache import require_redis
from app.core.client_ip import ClientAddress
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

LOGIN_PREFIX = "heliox:login:v2:"

LOGIN_RATE_WINDOW = 60  # seconds
LOGIN_RATE_LIMIT = _settings.RATE_LIMIT_LOGIN_ATTEMPTS  # one account from one client
LOGIN_ACCOUNT_RATE_LIMIT = 10  # one account from all clients
LOGIN_CLIENT_RATE_LIMIT = 30  # one client, any accounts
LOGIN_SHARED_PROXY_RATE_LIMIT = 300  # an unidentified-client proxy, any accounts

LOGIN_CAPTCHA_AFTER = 3  # account failures before CAPTCHA
LOGIN_LOCKOUT_AFTER = _settings.LOGIN_LOCKOUT_AFTER  # account failures before lockout
LOGIN_LOCKOUT_SECONDS = _settings.LOGIN_LOCKOUT_MINUTES * 60
LOGIN_CLIENT_CAPTCHA_AFTER = 10  # client failures (any accounts) before CAPTCHA
LOGIN_CLIENT_LOCKOUT_AFTER = 20  # client failures (any accounts) before lockout

ClientLike = Union[ClientAddress, str]


def _client(client: ClientLike) -> ClientAddress:
    return client if isinstance(client, ClientAddress) else ClientAddress(ip=str(client))


def _h(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:32]


def _account(email: str) -> str:
    return _h(email.strip().lower())


def _client_part(client: ClientAddress) -> str:
    return ("shared:" if client.shared else "") + _h(client.bucket)


def check_login_rate_limit(client: ClientLike, email: str = "") -> tuple[bool, int]:
    """
    Count this attempt against the per-account, per-client and combined windows.
    Returns (is_limited, retry_after_seconds).
    Raises HTTP 503 if Redis is unavailable.
    """
    client = _client(client)
    redis_client = require_redis()
    now = int(time.time())
    window_start = now - (now % LOGIN_RATE_WINDOW)
    who = _client_part(client)
    account = _account(email)

    client_limit = LOGIN_SHARED_PROXY_RATE_LIMIT if client.shared else LOGIN_CLIENT_RATE_LIMIT
    limits = [(f"{LOGIN_PREFIX}rate:client:{who}:{window_start}", client_limit)]
    if email:
        limits += [
            (f"{LOGIN_PREFIX}rate:pair:{who}:{account}:{window_start}", LOGIN_RATE_LIMIT),
            (f"{LOGIN_PREFIX}rate:account:{account}:{window_start}", LOGIN_ACCOUNT_RATE_LIMIT),
        ]

    pipe = redis_client.pipeline()
    for key, _ in limits:
        pipe.incr(key)
        pipe.expire(key, LOGIN_RATE_WINDOW * 2)
    counts = pipe.execute()[::2]

    if any(count > limit for count, (_, limit) in zip(counts, limits)):
        return True, max(1, window_start + LOGIN_RATE_WINDOW - now)
    return False, LOGIN_RATE_WINDOW


def is_locked_out(client: ClientLike, email: str = "") -> tuple[bool, int]:
    """
    Check if the account (or a non-shared client) is locked out.
    Returns (is_locked, remaining_seconds).
    Raises HTTP 503 if Redis is unavailable.
    """
    client = _client(client)
    redis_client = require_redis()
    keys = []
    if email:
        keys.append(f"{LOGIN_PREFIX}lock:account:{_account(email)}")
    if not client.shared:
        keys.append(f"{LOGIN_PREFIX}lock:client:{_client_part(client)}")
    remaining = max([redis_client.ttl(key) for key in keys] + [0])
    return (remaining > 0), max(remaining, 0)


def is_captcha_required(client: ClientLike, email: str = "") -> bool:
    """
    CAPTCHA is required after repeated failures on the account or from one client.
    Raises HTTP 503 if Redis is unavailable.
    """
    client = _client(client)
    redis_client = require_redis()
    if email and int(redis_client.get(f"{LOGIN_PREFIX}fail:account:{_account(email)}") or 0) >= LOGIN_CAPTCHA_AFTER:
        return True
    if not client.shared:
        client_failures = int(redis_client.get(f"{LOGIN_PREFIX}fail:client:{_client_part(client)}") or 0)
        return client_failures >= LOGIN_CLIENT_CAPTCHA_AFTER
    return False


def verify_login_captcha(client: ClientLike, captcha_token: str) -> bool:
    """
    Server-side hCaptcha verification for one login attempt. A solved CAPTCHA lets
    this attempt through; it doesn't reset failure counters or lockouts.
    """
    from app.auth.captcha_verify import verify_captcha_token

    if not captcha_token or not captcha_token.strip():
        return False
    client = _client(client)
    return verify_captcha_token(captcha_token.strip(), remote_ip=None if client.shared else client.ip)


def record_login_attempt(client: ClientLike, email: str, success: bool) -> tuple[bool, bool, int]:
    """
    Record login attempt. Returns (is_locked_out, captcha_required, lockout_remaining_seconds).
    Raises HTTP 503 if Redis is unavailable.
    """
    client = _client(client)
    redis_client = require_redis()
    account = _account(email)
    account_key = f"{LOGIN_PREFIX}fail:account:{account}"
    client_key = f"{LOGIN_PREFIX}fail:client:{_client_part(client)}"

    if success:
        # Client-level failures are kept: succeeding on one's own account must not
        # reset the counters of someone spraying other accounts from the same client.
        redis_client.delete(account_key)
        return False, False, 0

    pipe = redis_client.pipeline()
    pipe.incr(account_key)
    pipe.expire(account_key, LOGIN_LOCKOUT_SECONDS)
    if not client.shared:
        pipe.incr(client_key)
        pipe.expire(client_key, LOGIN_LOCKOUT_SECONDS)
    results = pipe.execute()
    account_failures = results[0]
    client_failures = results[2] if not client.shared else 0

    locked = False
    if account_failures >= LOGIN_LOCKOUT_AFTER:
        redis_client.setex(f"{LOGIN_PREFIX}lock:account:{account}", LOGIN_LOCKOUT_SECONDS, "1")
        locked = True
    if client_failures >= LOGIN_CLIENT_LOCKOUT_AFTER:
        redis_client.setex(f"{LOGIN_PREFIX}lock:client:{_client_part(client)}", LOGIN_LOCKOUT_SECONDS, "1")
        locked = True
    if locked:
        _alert_brute_force(client, email, client_failures, account_failures)
        return True, True, LOGIN_LOCKOUT_SECONDS

    captcha_required = account_failures >= LOGIN_CAPTCHA_AFTER or client_failures >= LOGIN_CLIENT_CAPTCHA_AFTER
    return False, captcha_required, 0


def _alert_brute_force(client: ClientAddress, email: str, client_failures: int, account_failures: int) -> None:
    """Log brute force lockout for alerting."""
    logger.warning(
        "Brute force lockout triggered",
        extra={
            "client_ip": client.ip,
            "client_shared": client.shared,
            "email_hash": hashlib.sha256(email.lower().encode()).hexdigest()[:12],
            "ip_attempts": client_failures,
            "email_attempts": account_failures,
        },
    )
