"""Anomaly detection endpoint."""
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from typing import Union
from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.db import get_db
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.team_api_key import TeamAPIKey
from app.schemas.anomaly import AnomalyResponse
from app.schemas.explainability import Component
from app.services.explainability import explain_metric
from app.services.anomaly import AnomalyDetectionService

router = APIRouter()


@router.get("", response_model=AnomalyResponse, summary="Detect spend/utilization anomalies")
def get_anomalies(
    include_explain: bool = Query(False, description="Include metric explainability payload"),
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
) -> Any:
    team_id = get_effective_team_id(auth_ctx)
    service = AnomalyDetectionService(db)
    result = service.detect(team_id=team_id)
    record_api_usage(db, team_id=team_id, endpoint="anomalies")
    payload = result.__dict__
    if include_explain:
        payload["breach_probability_explain"] = explain_metric(
            value=round(result.breach_probability, 2),
            unit="ratio",
            window="current month",
            formula="logistic risk model over projected spend vs budget",
            components=[
                Component(name="projected_monthly_spend", value=result.projected_monthly_spend, unit="USD", source="cost_snapshots"),
                Component(name="budget_usd_monthly", value=result.budget_usd_monthly or 0, unit="USD", source="team_budget"),
            ],
            assumptions=["Risk model uses recent spend trends and baseline window."],
            inputs={
                "data_points": 14,
                "window_days": 14,
                "telemetry_coverage": 1.0 if result.projected_monthly_spend > 0 else 0.5,
            },
        )
        point_explain = {}
        for anomaly in payload.get("anomalies", []):
            if "baseline_mean" in anomaly and "baseline_std" in anomaly:
                anomaly["baseline_window_days"] = AnomalyDetectionService.BASELINE_DAYS
                anomaly["spike_std_multiplier"] = AnomalyDetectionService.SPIKE_STD_MULTIPLIER
                point_explain[anomaly["type"]] = explain_metric(
                    value=anomaly.get("value", 0.0),
                    unit="USD" if anomaly.get("type") == "spend_spike" else "GPU hours",
                    window=f"baseline {AnomalyDetectionService.BASELINE_DAYS}d",
                    formula="latest_value > mean + spike_std_multiplier * std",
                    components=[
                        Component(name="baseline_mean", value=anomaly.get("baseline_mean", 0.0), unit="value", source="baseline"),
                        Component(name="baseline_std", value=anomaly.get("baseline_std", 0.0), unit="value", source="baseline"),
                        Component(name="spike_std_multiplier", value=AnomalyDetectionService.SPIKE_STD_MULTIPLIER, unit="x", source="config"),
                    ],
                    assumptions=["Spike detection uses trailing baseline window."],
                    inputs={
                        "data_points": AnomalyDetectionService.BASELINE_DAYS,
                        "window_days": AnomalyDetectionService.BASELINE_DAYS,
                        "telemetry_coverage": 1.0,
                    },
                )
        if point_explain:
            payload["point_explain"] = point_explain
    return payload
