"""Main FastAPI application with health checks and global error handling."""
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import check_db_connection, get_db
from app.core.logging import get_request_id, set_request_id, setup_logging
from app.core.rate_limit import RateLimitMiddleware

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
    
    logger.info(f"Startup complete - Database: {db_status}")
    logger.info("=" * 60)
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Heliox-AI Backend API",
    lifespan=lifespan,
)


# Rate Limiting (applied before other middleware)
app.add_middleware(RateLimitMiddleware)
logger.info("Rate limiting middleware enabled")

# CORS Configuration
if settings.CORS_ENABLED:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {settings.CORS_ORIGINS}")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Middleware for request ID tracking and request/response logging.
    
    Generates a unique request ID and logs request/response for observability.
    """
    # Get or generate request ID
    request_id = request.headers.get("X-Request-ID", get_request_id())
    set_request_id(request_id)
    
    # Log request (skip health checks to reduce noise)
    if request.url.path not in ["/health", "/health/db"]:
        logger.debug(
            f"Request: {request.method} {request.url.path}",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path}
        )
    
    # Process request
    response = await call_next(request)
    
    # Log response status (skip health checks to reduce noise)
    if request.url.path not in ["/health", "/health/db"]:
        logger.debug(
            f"Response: {request.method} {request.url.path} {response.status_code}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code
            }
        )
    
    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unhandled errors.
    
    Returns consistent JSON error response with request ID.
    """
    request_id = get_request_id()
    
    logger.error(
        f"Unhandled exception: {str(exc)}",
        exc_info=True,
        extra={"request_id": request_id, "path": request.url.path}
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": request_id,
        }
    )


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
            "status_code": exc.status_code
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.status_code,
            **error_details,
            "request_id": request_id,
        },
        headers=exc.headers or {}
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handler for request validation errors.
    
    Returns detailed validation error information.
    """
    request_id = get_request_id()
    
    logger.warning(
        f"Validation error: {exc.errors()}",
        extra={"request_id": request_id, "path": request.url.path}
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "message": "Request validation failed",
            "details": exc.errors(),
            "request_id": request_id,
        }
    )


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Basic health check endpoint.
    
    Returns:
        dict: Status indicating service is running
    """
    return {"status": "ok"}


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
                "message": "Database connection is healthy"
            }
        else:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "error",
                    "database": "disconnected",
                    "message": "Database connection failed"
                }
            )
    except Exception as e:
        logger.warning(
            "Database health check error",
            exc_info=True,
            extra={"error_type": type(e).__name__}
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "database": "error",
                "message": "Database health check failed"
            }
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

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True if settings.ENV == "dev" else False,
        log_level=settings.LOG_LEVEL.lower(),
    )

