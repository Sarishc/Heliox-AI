"""Observability: OpenTelemetry tracing, Prometheus metrics, Sentry."""
import logging
from typing import Optional

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def init_sentry() -> None:
    """Initialize Sentry error monitoring."""
    if not settings.SENTRY_DSN:
        logger.debug("Sentry disabled (no SENTRY_DSN)")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT or settings.ENV,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            send_default_pii=False,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("Sentry initialized")
    except Exception as e:
        logger.warning(f"Sentry init failed: {e}")


def init_opentelemetry() -> None:
    """Initialize OpenTelemetry tracing (uses OTEL_* env vars)."""
    if not settings.OTEL_ENABLED:
        logger.debug("OpenTelemetry disabled")
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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
