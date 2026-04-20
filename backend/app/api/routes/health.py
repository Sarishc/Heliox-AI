"""Comprehensive health check endpoint for ECS container health checks and monitoring."""
import time
import logging
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.db import check_db_connection, get_db
from app.core.cache import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()

VERSION = "1.0.0"


@router.get(
    "",
    summary="Health check",
    description=(
        "Checks database, Redis, and Celery. "
        "Returns HTTP 200 when healthy, HTTP 503 when any critical check fails. "
        "Used as the ECS container health check target."
    ),
    tags=["Health"],
)
def health_check() -> Any:
    checks: Dict[str, Any] = {}
    overall = "healthy"

    # Database
    t0 = time.monotonic()
    try:
        db_ok = check_db_connection()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        if db_ok:
            checks["database"] = {"status": "ok", "latency_ms": latency_ms}
        else:
            checks["database"] = {"status": "error", "latency_ms": latency_ms}
            overall = "unhealthy"
    except Exception as e:
        checks["database"] = {"status": "error", "error": type(e).__name__}
        overall = "unhealthy"

    # Redis
    t0 = time.monotonic()
    try:
        rc = get_redis()
        if rc is not None:
            rc.ping()
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            checks["redis"] = {"status": "ok", "latency_ms": latency_ms}
        else:
            checks["redis"] = {"status": "error", "error": "connection_failed"}
            overall = "unhealthy"
    except Exception as e:
        checks["redis"] = {"status": "error", "error": type(e).__name__}
        overall = "unhealthy"

    # Celery (best-effort — degraded if unavailable, not unhealthy)
    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=1.0)
        active = inspect.active()
        checks["celery"] = {"status": "ok" if active is not None else "degraded"}
        if active is None and overall == "healthy":
            overall = "degraded"
    except Exception as e:
        checks["celery"] = {"status": "degraded", "error": type(e).__name__}
        if overall == "healthy":
            overall = "degraded"

    body = {"status": overall, "checks": checks, "version": VERSION}
    http_status = 200 if overall in ("healthy", "degraded") else 503
    # ECS marks the container unhealthy on non-2xx; return 503 only when DB or Redis are down
    if overall == "unhealthy":
        http_status = 503

    return JSONResponse(status_code=http_status, content=body)
