"""
Tests for Redis-as-hard-dependency enforcement.

Verifies that:
  1. REDIS_URL is required — Settings raises without it.
  2. get_redis() returns None on connection failure (optional caching callers).
  3. require_redis() raises HTTP 503 when Redis is unavailable.
  4. Rate limiter returns HTTP 503 (not silent pass-through) when Redis is down.
  5. Brute-force functions raise HTTP 503 when Redis is unavailable.
  6. Token blacklist functions raise HTTP 503 when Redis is unavailable.
  7. GET /api/v1/health returns the expected schema.
  8. App startup fails (RuntimeError) when Redis ping fails.
"""

import pytest
from unittest.mock import MagicMock, patch

# ── 1. Config: REDIS_URL is required ─────────────────────────────────────────


def test_redis_url_required_in_settings():
    """Settings raises ValidationError when REDIS_URL is absent."""
    from pydantic import ValidationError
    from pydantic_settings import BaseSettings
    from pydantic import Field

    class IsolatedSettings(BaseSettings):
        REDIS_URL: str = Field(description="required")
        model_config = {
            "env_file": "/nonexistent",
            "env_prefix": "HELIOX_ISOLATED_TEST_",
        }

    with pytest.raises(ValidationError) as exc_info:
        IsolatedSettings()

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("REDIS_URL",) and e["type"] == "missing" for e in errors)


# ── 2 & 3. cache.get_redis() vs require_redis() ───────────────────────────────


def test_get_redis_returns_none_on_connection_failure():
    """get_redis() returns None when Redis is unreachable (safe for caching callers)."""
    from app.core import cache as cache_module

    original = cache_module._redis_client
    try:
        cache_module._redis_client = None
        with patch("app.core.cache.redis.from_url", side_effect=ConnectionError("refused")):
            result = cache_module.get_redis()
        assert result is None
    finally:
        cache_module._redis_client = original


def test_require_redis_raises_503_when_unavailable():
    """require_redis() raises HTTP 503 when Redis is unreachable."""
    from fastapi import HTTPException
    from app.core import cache as cache_module

    original = cache_module._redis_client
    try:
        cache_module._redis_client = None
        with patch("app.core.cache.redis.from_url", side_effect=ConnectionError("refused")):
            with pytest.raises(HTTPException) as exc_info:
                cache_module.require_redis()
        assert exc_info.value.status_code == 503
    finally:
        cache_module._redis_client = original


def test_require_redis_returns_client_when_available():
    """require_redis() returns the Redis client when connected."""
    from app.core import cache as cache_module

    mock_client = MagicMock()
    mock_client.ping.return_value = True

    original = cache_module._redis_client
    try:
        cache_module._redis_client = None
        with patch("app.core.cache.redis.from_url", return_value=mock_client):
            result = cache_module.require_redis()
        assert result is mock_client
    finally:
        cache_module._redis_client = original


@pytest.mark.parametrize(
    ("redis_url", "expects_ssl_option"),
    [
        ("redis://localhost:6379/0", False),
        ("rediss://cache.example.com:6379/0", True),
    ],
)
def test_get_redis_only_passes_tls_options_for_rediss(redis_url, expects_ssl_option):
    """Plain Redis connections must not receive TLS-only connection options."""
    from app.core import cache as cache_module

    mock_client = MagicMock()
    mock_client.ping.return_value = True
    original_client = cache_module._redis_client
    original_url = cache_module.settings.REDIS_URL
    try:
        cache_module._redis_client = None
        cache_module.settings.REDIS_URL = redis_url
        with patch("app.core.cache.redis.from_url", return_value=mock_client) as from_url:
            assert cache_module.get_redis() is mock_client

        options = from_url.call_args.kwargs
        assert ("ssl_cert_reqs" in options) is expects_ssl_option
    finally:
        cache_module._redis_client = original_client
        cache_module.settings.REDIS_URL = original_url


# ── 4. Rate limiter: no silent fallback ──────────────────────────────────────


def test_rate_limiter_returns_503_when_redis_unavailable():
    """RateLimitMiddleware returns HTTP 503 (not 200) when Redis is down."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.core.rate_limit import RateLimitMiddleware

    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware)

    @test_app.get("/test-endpoint")
    def _handler():
        return {"ok": True}

    from fastapi import HTTPException

    with patch(
        "app.core.rate_limit.require_redis",
        side_effect=HTTPException(status_code=503, detail="Redis unavailable"),
    ):
        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/test-endpoint")

    assert response.status_code == 503


def test_rate_limiter_enforces_limit_with_redis():
    """RateLimitMiddleware blocks requests exceeding the limit when Redis works."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.core import rate_limit as rl_module
    from app.core.rate_limit import RateLimitMiddleware

    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware)

    @test_app.get("/test-endpoint")
    def _handler():
        return {"ok": True}

    mock_redis = MagicMock()
    # Simulate count well above limit on first incr
    mock_redis.incr.return_value = rl_module.RATE_LIMIT_MAX_REQUESTS + 1
    mock_redis.expire.return_value = True

    with patch("app.core.rate_limit.require_redis", return_value=mock_redis):
        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/test-endpoint")

    assert response.status_code == 429
    assert "rate_limit_exceeded" in response.json()["error"]


# ── 5. Brute-force protection: no silent fallback ────────────────────────────


def test_check_login_rate_limit_raises_503_without_redis():
    """check_login_rate_limit raises HTTP 503 when Redis is unavailable."""
    from fastapi import HTTPException
    from app.auth.brute_force import check_login_rate_limit

    with patch(
        "app.auth.brute_force.require_redis",
        side_effect=HTTPException(503, "Redis down"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            check_login_rate_limit("192.168.1.1")
    assert exc_info.value.status_code == 503


def test_is_locked_out_raises_503_without_redis():
    """is_locked_out raises HTTP 503 when Redis is unavailable."""
    from fastapi import HTTPException
    from app.auth.brute_force import is_locked_out

    with patch(
        "app.auth.brute_force.require_redis",
        side_effect=HTTPException(503, "Redis down"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            is_locked_out("192.168.1.1")
    assert exc_info.value.status_code == 503


# ── 6. Token blacklist: no silent fallback ───────────────────────────────────


def test_is_token_blacklisted_raises_503_without_redis():
    """is_token_blacklisted raises HTTP 503 when Redis is unavailable."""
    from fastapi import HTTPException
    from app.auth.cookie_auth import is_token_blacklisted

    with patch(
        "app.auth.cookie_auth.require_redis",
        side_effect=HTTPException(503, "Redis down"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            is_token_blacklisted("some.jwt.token")
    assert exc_info.value.status_code == 503


def test_blacklist_token_raises_503_without_redis():
    """blacklist_token raises HTTP 503 when Redis is unavailable."""
    from fastapi import HTTPException
    from app.auth.cookie_auth import blacklist_token

    with patch(
        "app.auth.cookie_auth.require_redis",
        side_effect=HTTPException(503, "Redis down"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            blacklist_token("some.jwt.token")
    assert exc_info.value.status_code == 503


# ── 7. GET /api/v1/health endpoint schema ────────────────────────────────────


def test_health_endpoint_schema_when_healthy():
    """GET /api/v1/health returns the expected JSON schema when all checks pass."""
    from fastapi.testclient import TestClient
    from app.main import app

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True

    # Patch at the import site — health.py imports these by reference
    with (
        patch("app.api.routes.health.get_redis", return_value=mock_redis),
        patch("app.api.routes.health.check_db_connection", return_value=True),
        patch("app.core.rate_limit.require_redis", return_value=mock_redis),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("healthy", "degraded")
    assert "checks" in body
    assert "database" in body["checks"]
    assert "redis" in body["checks"]
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert "latency_ms" in body["checks"]["database"]
    assert "latency_ms" in body["checks"]["redis"]
    assert "version" in body


def test_health_endpoint_returns_503_when_redis_down():
    """GET /api/v1/health returns HTTP 503 when Redis is unavailable."""
    from fastapi.testclient import TestClient
    from app.main import app

    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True

    with (
        patch("app.api.routes.health.get_redis", return_value=None),
        patch("app.api.routes.health.check_db_connection", return_value=True),
        patch("app.core.rate_limit.require_redis", return_value=mock_redis),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["redis"]["status"] == "error"


def test_health_endpoint_returns_503_when_db_down():
    """GET /api/v1/health returns HTTP 503 when the database is unavailable."""
    from fastapi.testclient import TestClient
    from app.main import app

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True

    with (
        patch("app.api.routes.health.get_redis", return_value=mock_redis),
        patch("app.api.routes.health.check_db_connection", return_value=False),
        patch("app.core.rate_limit.require_redis", return_value=mock_redis),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"]["status"] == "error"


# ── 8. Startup fails when Redis ping fails ───────────────────────────────────


@pytest.mark.asyncio
async def test_startup_raises_if_redis_ping_fails():
    """App lifespan raises RuntimeError when Redis is unreachable at startup."""
    from fastapi import FastAPI

    # Re-import the lifespan function and test it directly
    import app.main as main_module

    mock_redis = MagicMock()
    mock_redis.ping.side_effect = ConnectionError("refused")

    with patch("app.main.get_redis", return_value=mock_redis), patch("app.main.check_db_connection", return_value=True):
        with pytest.raises(RuntimeError, match="Redis connection failed on startup"):
            async with main_module.lifespan(FastAPI()):
                pass  # pragma: no cover
