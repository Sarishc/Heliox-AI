"""Explainability helper for metric outputs."""
from __future__ import annotations

from typing import Any

from app.schemas.explainability import Component, Explanation, MetricValue


def _confidence_score(inputs: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 1.0

    data_points = int(inputs.get("data_points", 0))
    window_days = int(inputs.get("window_days", 0))
    if window_days and data_points < max(3, int(window_days * 0.5)):
        reasons.append("SPARSE_WINDOW")
        score -= 0.3

    telemetry_coverage = float(inputs.get("telemetry_coverage", 1.0))
    if telemetry_coverage < 0.8:
        reasons.append("MISSING_TELEMETRY")
        score -= 0.2

    if inputs.get("default_rate_used"):
        reasons.append("DEFAULT_RATE_USED")
        score -= 0.2

    if inputs.get("estimated_power"):
        reasons.append("ESTIMATED_POWER")
        score -= 0.1

    score = max(0.1, min(1.0, score))
    return score, reasons


def explain_metric(
    *,
    value: float | int,
    unit: str,
    window: str,
    formula: str,
    components: list[Component],
    assumptions: list[str],
    inputs: dict[str, Any],
) -> MetricValue:
    confidence, reasons = _confidence_score(inputs)
    return MetricValue(
        value=value,
        unit=unit,
        window=window,
        confidence=round(confidence, 2),
        confidence_reasons=reasons,
        explanation=Explanation(
            formula=formula,
            components=components,
            assumptions=assumptions,
        ),
    )
