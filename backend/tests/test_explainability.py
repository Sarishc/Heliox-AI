"""Tests for metric explainability helper."""

from app.services.explainability import explain_metric
from app.schemas.explainability import Component


def test_explain_metric_shape():
    metric = explain_metric(
        value=100,
        unit="USD",
        window="2026-01-01 to 2026-01-07",
        formula="sum(cost_usd)",
        components=[Component(name="cost_sum", value=100, unit="USD", source="cost_snapshots")],
        assumptions=["Cost snapshots complete."],
        inputs={"data_points": 7, "window_days": 7},
    )
    assert metric.value == 100
    assert metric.unit == "USD"
    assert metric.explanation.formula
    assert metric.confidence >= 0.1


def test_confidence_reasons():
    metric = explain_metric(
        value=50,
        unit="USD",
        window="2026-01-01 to 2026-01-03",
        formula="sum(cost_usd)",
        components=[Component(name="cost_sum", value=50, unit="USD", source="cost_snapshots")],
        assumptions=["Cost snapshots complete."],
        inputs={
            "data_points": 2,
            "window_days": 7,
            "telemetry_coverage": 0.5,
            "default_rate_used": True,
        },
    )
    assert "SPARSE_WINDOW" in metric.confidence_reasons
    assert "MISSING_TELEMETRY" in metric.confidence_reasons
    assert "DEFAULT_RATE_USED" in metric.confidence_reasons
