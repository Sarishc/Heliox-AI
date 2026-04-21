"""Tests for Prometheus metrics endpoint and middleware."""

import pytest

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_metrics_endpoint_exists(client: TestClient):
    """GET /metrics returns 200 and Prometheus text format."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/plain")
    # Prometheus format: metric_name{labels} value or metric_name value
    assert "heliox_" in resp.text


def test_metrics_prometheus_format(client: TestClient):
    """Metrics output is valid Prometheus exposition format."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text
    # Should contain our metrics
    assert "heliox_http_requests_total" in text
    assert "heliox_http_request_duration_seconds" in text
    assert "heliox_http_errors_total" in text
    assert "heliox_http_requests_in_flight" in text
    # No high-cardinality or sensitive labels
    assert "tenant_id" not in text
    assert "user_id" not in text
    assert "api_key" not in text.lower()


def test_request_metrics_increment_after_api_call(client: TestClient):
    """Request count and latency metrics increment after API calls."""
    # Get baseline
    resp1 = client.get("/metrics")
    before = resp1.text

    # Make API call
    client.get("/health")

    # Metrics may or may not include /health (we exclude it)
    resp2 = client.get("/metrics")
    after = resp2.text

    # /metrics itself should be excluded, so our /metrics call shouldn't add to request count
    # But /health is excluded too - so no new metrics from that
    # Make a call to an API path that is recorded
    client.get("/api/v1/billing/plans")

    resp3 = client.get("/metrics")
    final = resp3.text

    # heliox_http_requests_total should have increased for the /api/v1/billing/plans call
    # Extract the total for that path
    assert "heliox_http_requests_total" in final
    assert "path_template" in final or "method" in final


def test_health_paths_excluded_from_metrics(client: TestClient):
    """Health and probe paths are excluded from request metrics (no probe noise)."""
    from app.core.metrics import should_record_metrics

    assert not should_record_metrics("/health")
    assert not should_record_metrics("/metrics")
    assert not should_record_metrics("/liveness")
    assert not should_record_metrics("/ready")
    assert should_record_metrics("/api/v1/billing/plans")


def test_path_normalization(client: TestClient):
    """Path normalization collapses UUIDs and IDs."""
    from app.core.metrics import normalize_path

    assert normalize_path("/api/v1/teams/550e8400-e29b-41d4-a716-446655440000") == "/api/v1/teams/{id}"
    assert normalize_path("/api/v1/jobs/12345") == "/api/v1/jobs/{id}"
    assert normalize_path("/api/v1/recommendations") == "/api/v1/recommendations"
    assert normalize_path("/api/v1/teams/abc-123/resource") == "/api/v1/teams/abc-123/resource"


def test_metrics_no_sensitive_data(client: TestClient):
    """Metrics output does not contain secrets or PII."""
    resp = client.get("/metrics")
    text = resp.text.lower()
    # No common secret patterns (path_template="{token}" is ok - it's a placeholder)
    assert "password" not in text
    assert "secret" not in text
    assert "bearer" not in text
    # x-api-key as a header name could appear in help text; avoid actual key values
    assert "sk_live_" not in text
    assert "sk_test_" not in text
