"""Main FastAPI application with health checks and global error handling."""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import check_db_connection
from app.core.logging import get_request_id, set_request_id, setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.cache import get_redis

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    setup_logging()
    from app.core.observability import init_sentry, init_opentelemetry

    init_sentry()
    init_opentelemetry()
    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Environment: {settings.ENV}")
    logger.info(f"Log level: {settings.LOG_LEVEL}")
    logger.info(f"Port: {settings.PORT}")

    # Production safety: Validate database connection on startup (fail fast)
    db_status = "unknown"
    if settings.ENV in ("production", "staging"):
        logger.info("Validating database connection on startup...")
        if check_db_connection():
            db_status = "connected"
            logger.info("✓ Database connection validated successfully")
        else:
            logger.error("✗ Database connection failed on startup - aborting")
            raise RuntimeError("Database connection failed on startup. Check DATABASE_URL configuration.")
    else:
        # In dev, check but don't fail
        if check_db_connection():
            db_status = "connected"
            logger.info("✓ Database connection: OK")
        else:
            db_status = "disconnected"
            logger.warning("⚠ Database connection: FAILED (continuing in dev mode)")

    # Redis: hard required — app must not start without a working Redis connection
    logger.info("Validating Redis connection on startup...")
    try:
        from urllib.parse import urlparse

        parsed = urlparse(settings.REDIS_URL)
        redis_host = parsed.hostname or settings.REDIS_URL
        redis_port = parsed.port or 6379
        rc = get_redis()
        if rc is None:
            raise RuntimeError("Redis client could not be created")
        rc.ping()
        logger.info("✓ Redis connection verified at %s:%s", redis_host, redis_port)
    except Exception as e:
        logger.error("✗ Redis connection failed on startup - aborting: %s", e)
        raise RuntimeError(
            f"Redis connection failed on startup: {e}. " "Set REDIS_URL to your ElastiCache primary endpoint."
        )

    logger.info(f"Startup complete - Database: {db_status}, Redis: connected")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")


# Initialize FastAPI app
app = FastAPI(
    title="Heliox API",
    version="1.0.0",
    description="GPU cost visibility and optimization for ML infrastructure teams.",
    lifespan=lifespan,
)


# Security headers (HTTPS redirect, HSTS, CSP, etc.)
from app.middleware.security_headers import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)

# CSRF protection for cookie-authenticated state-changing requests
from app.middleware.csrf import CSRFMiddleware

app.add_middleware(CSRFMiddleware)

# Tenant context (injects tenant_id into request.state when resolved by auth)
from app.middleware.tenant_context import TenantContextMiddleware

app.add_middleware(TenantContextMiddleware)

# Rate Limiting (100/min per user, IP fallback)
app.add_middleware(RateLimitMiddleware)
logger.info("Rate limiting middleware enabled")

# Usage Tracking Middleware
from app.middleware.usage_tracking import UsageTrackingMiddleware

app.add_middleware(
    UsageTrackingMiddleware,
    sample_rate=(settings.USAGE_METERING_SAMPLE_RATE if hasattr(settings, "USAGE_METERING_SAMPLE_RATE") else 1.0),
)
logger.info(f"Usage tracking middleware enabled (sample_rate={getattr(settings, 'USAGE_METERING_SAMPLE_RATE', 1.0)})")

# Entitlement Check Middleware
from app.middleware.entitlement_check import EntitlementCheckMiddleware

app.add_middleware(EntitlementCheckMiddleware)
logger.info("Entitlement check middleware enabled")

# Demo mode: block writes on the demo tenant when DEMO_MODE=True
if settings.DEMO_MODE:
    from app.core.demo_guard import DemoModeMiddleware

    app.add_middleware(DemoModeMiddleware)
    logger.info("Demo mode middleware enabled (tenant=%s)", settings.DEMO_TENANT_ID or "not-set")

# CORS Configuration
if settings.CORS_ENABLED:
    origins = settings.CORS_ORIGINS
    if not origins and settings.ENV == "dev":
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {origins}")


SLOW_QUERY_THRESHOLD_MS = 200


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Middleware for correlation ID, Prometheus metrics, request logging, and slow query profiling.
    Records metrics even when handlers raise (5xx); excludes health/probe paths.
    """
    import time

    start_time = time.perf_counter()
    # Correlation ID: X-Correlation-ID or X-Request-ID (Kubernetes/standard)
    correlation_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID") or get_request_id()
    set_request_id(correlation_id)

    path = request.url.path
    from app.core.metrics import METRICS_EXCLUDED_PATHS

    record_metrics = path not in METRICS_EXCLUDED_PATHS

    if record_metrics:
        logger.debug(
            f"Request: {request.method} {path}",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": path,
            },
        )

    # Prometheus: increment in-flight for non-excluded paths
    path_template = None
    if record_metrics:
        from app.core.metrics import (
            IN_FLIGHT_REQUESTS,
            normalize_path,
        )

        path_template = normalize_path(path)
        IN_FLIGHT_REQUESTS.labels(method=request.method, path_template=path_template).inc()

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        # Handler raised - exception handler will return 500; record as 5xx
        status_code = 500
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        elapsed_sec = elapsed_ms / 1000.0

        # Prometheus metrics (always record for API paths, including 5xx from exceptions)
        if record_metrics and path_template is not None:
            from app.core.metrics import (
                IN_FLIGHT_REQUESTS,
                REQUEST_COUNT,
                REQUEST_LATENCY,
                ERROR_COUNT,
                get_status_class,
                normalize_path,
            )

            pt = path_template or normalize_path(path)
            IN_FLIGHT_REQUESTS.labels(method=request.method, path_template=pt).dec()
            status_class = get_status_class(status_code)
            REQUEST_COUNT.labels(
                method=request.method,
                path_template=pt,
                status_class=status_class,
            ).inc()
            REQUEST_LATENCY.labels(
                method=request.method,
                path_template=pt,
            ).observe(elapsed_sec)
            if status_class == "5xx":
                ERROR_COUNT.labels(
                    method=request.method,
                    path_template=pt,
                ).inc()

        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            logger.warning(
                f"SLOW REQUEST: {request.method} {path} took {elapsed_ms:.0f}ms (threshold: {SLOW_QUERY_THRESHOLD_MS}ms)",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": path,
                    "duration_ms": round(elapsed_ms),
                    "status_code": status_code,
                },
            )
        elif record_metrics:
            logger.debug(
                f"Response: {request.method} {path} {status_code}",
                extra={
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": path,
                    "status_code": status_code,
                },
            )

    response.headers["X-Request-ID"] = correlation_id
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Response-Time-Ms"] = str(round(elapsed_ms))
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unhandled errors.
    Reports to Sentry and returns consistent JSON error response.
    """
    request_id = get_request_id()
    logger.error(
        f"Unhandled exception: {str(exc)}",
        exc_info=True,
        extra={"correlation_id": request_id, "path": request.url.path},
    )
    if settings.SENTRY_DSN and settings.ENV != "test":
        try:
            import sentry_sdk

            with sentry_sdk.push_scope() as scope:
                scope.set_tag("request_id", request_id)
                scope.set_tag("correlation_id", request_id)
                sentry_sdk.capture_exception(exc)
        except Exception:
            pass
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": request_id,
        },
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handler for HTTP exceptions.

    Ensures consistent error response format across all HTTPExceptions.
    """
    request_id = get_request_id()

    # Extract detail (can be str or dict)
    detail = exc.detail
    if isinstance(detail, dict):
        error_message = detail.get("message", "An error occurred")
        error_details = detail
    else:
        error_message = str(detail)
        error_details = {"message": error_message}

    # Log the error (without sensitive data)
    logger.warning(
        f"HTTP {exc.status_code}: {error_message}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "status_code": exc.status_code,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.status_code,
            **error_details,
            "request_id": request_id,
        },
        headers=exc.headers or {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handler for request validation errors.

    Returns detailed validation error information.
    """
    request_id = get_request_id()

    logger.warning(
        f"Validation error: {exc.errors()}",
        extra={"request_id": request_id, "path": request.url.path},
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "message": "Request validation failed",
            "details": exc.errors(),
            "request_id": request_id,
        },
    )


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint (liveness).
    Returns 200 if the process is running.
    """
    return {"status": "ok"}


@app.get("/liveness", tags=["Health"])
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes liveness probe: process is alive.
    """
    return {"status": "ok"}


@app.get("/readiness", tags=["Health"])
async def readiness_alias() -> Dict[str, str]:
    """
    Alias for /ready - Kubernetes readiness probe.
    """
    return await readiness_check()


@app.get("/ready", tags=["Health"])
async def readiness_check() -> Dict[str, str]:
    """
    Readiness check: database + redis connectivity.
    """
    db_ok = check_db_connection()
    redis_client = get_redis()
    redis_ok = redis_client is not None
    if db_ok and redis_ok:
        return {"status": "ok", "database": "connected", "redis": "connected"}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "error",
            "database": "connected" if db_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
        },
    )


@app.get("/health/db", tags=["Health"])
async def health_check_db() -> Dict[str, Any]:
    """
    Database health check endpoint.

    Safely checks database connection without exposing sensitive information.

    Returns:
        dict: Database connection status with appropriate message
    """
    try:
        is_healthy = check_db_connection()

        if is_healthy:
            return {
                "status": "ok",
                "database": "connected",
                "message": "Database connection is healthy",
            }
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "error",
                    "database": "disconnected",
                    "message": "Database connection failed",
                },
            )
    except Exception as e:
        logger.warning(
            "Database health check error",
            exc_info=True,
            extra={"error_type": type(e).__name__},
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "database": "error",
                "message": "Database health check failed",
            },
        )


@app.get("/", tags=["Root"])
async def root() -> Dict[str, str]:
    """
    Root endpoint with API information.

    Returns:
        dict: API name and version (security: does not expose environment)
    """
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
    }


# Include API router
from app.api import api_router
from app.api.routes import share

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
app.include_router(share.router)


@app.get("/metrics", tags=["Observability"])
async def metrics():
    """Prometheus metrics endpoint."""
    from app.core.metrics import get_metrics

    data, content_type = get_metrics()
    from fastapi.responses import Response

    return Response(content=data, media_type=content_type)


# OpenTelemetry instrumentation (after routes)
from app.core.observability import instrument_app

instrument_app(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True if settings.ENV == "dev" else False,
        log_level=settings.LOG_LEVEL.lower(),
    )
