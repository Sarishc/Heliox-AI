"""Observability: OpenTelemetry tracing, Prometheus metrics, Sentry."""

import logging
from typing import Optional

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Headers and keys to scrub from Sentry events (never send to Sentry)
_SENTRY_SCRUB_HEADERS = frozenset(
    {
        "authorization",
        "x-api-key",
        "x-csrf-token",
        "cookie",
        "set-cookie",
        "proxy-authorization",
        "x-forwarded-authorization",
    }
)

# Keys to scrub from request data / context
_SENTRY_SCRUB_KEYS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "csrf",
        "credential",
        "webhook_url",
        "slack_webhook",
        "stripe_key",
        "encryption_key",
        "private_key",
    }
)


def _sentry_before_send(event: dict, hint: dict) -> Optional[dict]:
    """
    Scrub sensitive data before sending to Sentry.
    Removes auth headers, API keys, cookies, webhook URLs, and similar.
    """
    # Scrub request headers
    request = event.get("request")
    if request and isinstance(request.get("headers"), dict):
        headers = request["headers"]
        for key in list(headers.keys()):
            if key.lower() in _SENTRY_SCRUB_HEADERS:
                headers[key] = "[Filtered]"

    # Scrub cookies
    if request and "cookies" in request:
        request["cookies"] = "[Filtered]"

    # Scrub env vars that might contain secrets
    contexts = event.get("contexts", {})
    runtime = contexts.get("runtime")
    if isinstance(runtime, dict):
        env = runtime.get("env", {})
        if isinstance(env, dict):
            for key in list(env.keys()):
                if any(s in str(key).lower() for s in _SENTRY_SCRUB_KEYS):
                    env[key] = "[Filtered]"

    # Scrub extra/context that might have sensitive data
    extra = event.get("extra", {})
    if isinstance(extra, dict):
        for key in list(extra.keys()):
            if any(s in str(key).lower() for s in _SENTRY_SCRUB_KEYS):
                extra[key] = "[Filtered]"

    # Scrub URLs that might contain secrets (webhook URLs, etc.)
    if request and isinstance(request.get("url"), str):
        url = request["url"]
        if "webhook" in url.lower() or "hooks.slack" in url.lower():
            request["url"] = "[Filtered]"

    return event


def _should_enable_sentry() -> bool:
    """Only enable Sentry when DSN is set and not in test environment."""
    if not settings.SENTRY_DSN:
        return False
    if settings.ENV == "test":
        return False
    return True


def init_sentry() -> None:
    """Initialize Sentry error monitoring for FastAPI/API process."""
    if not _should_enable_sentry():
        logger.debug("Sentry disabled (no SENTRY_DSN or ENV=test)")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT or settings.ENV,
            release=settings.SENTRY_RELEASE or None,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            send_default_pii=False,
            max_request_body_size="never",  # Avoid sending request bodies (may contain secrets)
            before_send=_sentry_before_send,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry initialized (API)")
    except Exception as e:
        logger.warning(f"Sentry init failed: {e}")


def init_sentry_celery() -> None:
    """Initialize Sentry for Celery worker process. Call from worker_init signal."""
    if not _should_enable_sentry():
        logger.debug("Sentry disabled for Celery (no SENTRY_DSN or ENV=test)")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT or settings.ENV,
            release=settings.SENTRY_RELEASE or None,
            traces_sample_rate=0.1,
            send_default_pii=False,
            before_send=_sentry_before_send,
            integrations=[
                CeleryIntegration(monitor_beat_tasks=False),
            ],
        )
        logger.info("Sentry initialized (Celery)")
    except Exception as e:
        logger.warning(f"Sentry Celery init failed: {e}")


def init_opentelemetry() -> None:
    """Initialize OpenTelemetry tracing (uses OTEL_* env vars)."""
    if not settings.OTEL_ENABLED:
        logger.debug("OpenTelemetry disabled")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
        if not endpoint.endswith("/v1/traces"):
            endpoint = f"{endpoint}/v1/traces" if "/v1/" not in endpoint else endpoint
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("OpenTelemetry tracing initialized")
    except Exception as e:
        logger.warning(f"OpenTelemetry init failed: {e}")


def instrument_app(app):  # noqa: ANN001
    """Instrument FastAPI app with OpenTelemetry (call after app creation)."""
    if not settings.OTEL_ENABLED:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception as e:
        logger.warning(f"OpenTelemetry instrumentation failed: {e}")
