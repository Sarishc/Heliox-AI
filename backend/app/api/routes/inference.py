"""Inference span ingestion and cost-per-model query endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.core.tenant import get_effective_team_id
from app.core.usage_tracking import record_api_usage
from app.models.inference import InferenceSpan, ModelCostSummary
from app.models.team_api_key import TeamAPIKey

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_SPANS_PER_REQUEST = 1000


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class HelioxSpan(BaseModel):
    """Heliox simplified span format."""

    model_name: str = Field(..., max_length=255)
    serving_framework: str = Field(default="custom", max_length=50)
    request_id: str = Field(..., max_length=128)
    trace_id: Optional[str] = Field(default=None, max_length=128)
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)
    duration_ms: float = Field(..., ge=0)
    ttfb_ms: Optional[float] = Field(default=None, ge=0)
    started_at: datetime
    ended_at: Optional[datetime] = None
    cluster_name: Optional[str] = Field(default=None, max_length=200)
    model_version: Optional[str] = Field(default=None, max_length=100)
    gpu_type: Optional[str] = Field(default=None, max_length=100)
    gpu_count: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def set_ended_at(self) -> "HelioxSpan":
        if self.ended_at is None:
            from datetime import timedelta
            self.ended_at = self.started_at + timedelta(milliseconds=self.duration_ms)
        return self


class HelioxSpanBatch(BaseModel):
    """Heliox simplified format envelope."""

    spans: List[HelioxSpan]


# ── OTel OTLP helpers ─────────────────────────────────────────────────────────

def _str_attr(attrs: list, key: str) -> Optional[str]:
    for a in attrs:
        if a.get("key") == key:
            v = a.get("value", {})
            return v.get("stringValue") or v.get("string_value")
    return None


def _int_attr(attrs: list, key: str) -> Optional[int]:
    for a in attrs:
        if a.get("key") == key:
            v = a.get("value", {})
            raw = v.get("intValue") or v.get("int_value")
            if raw is not None:
                try:
                    return int(raw)
                except (ValueError, TypeError):
                    pass
    return None


def _parse_otlp(payload: dict, team_id: UUID) -> tuple[list[InferenceSpan], list[str]]:
    """Parse OTel OTLP JSON format into InferenceSpan objects."""
    spans: list[InferenceSpan] = []
    errors: list[str] = []

    for rs in payload.get("resourceSpans", []):
        resource_attrs = rs.get("resource", {}).get("attributes", [])
        service_name = _str_attr(resource_attrs, "service.name") or ""
        resource_model = _str_attr(resource_attrs, "model.name")

        for ss in rs.get("scopeSpans", []):
            for raw in ss.get("spans", []):
                span_attrs = raw.get("attributes", [])

                model_name = (
                    _str_attr(span_attrs, "llm.model_name")
                    or _str_attr(span_attrs, "gen_ai.request.model")
                    or resource_model
                    or service_name
                    or ""
                )
                if not model_name:
                    errors.append(
                        f"span {raw.get('spanId', '?')}: missing model_name; skipped"
                    )
                    continue

                # Timestamps — OTel uses Unix nanoseconds
                try:
                    start_ns = int(raw.get("startTimeUnixNano", 0))
                    end_ns = int(raw.get("endTimeUnixNano", 0))
                    started_at = datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc)
                    ended_at = datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc)
                    duration_ms = (end_ns - start_ns) / 1e6
                except (ValueError, OSError) as exc:
                    errors.append(f"span {raw.get('spanId', '?')}: bad timestamp — {exc}")
                    continue

                input_tok = (
                    _int_attr(span_attrs, "llm.usage.prompt_tokens")
                    or _int_attr(span_attrs, "gen_ai.usage.prompt_tokens")
                    or _int_attr(span_attrs, "gen_ai.usage.input_tokens")
                )
                output_tok = (
                    _int_attr(span_attrs, "llm.usage.completion_tokens")
                    or _int_attr(span_attrs, "gen_ai.usage.completion_tokens")
                    or _int_attr(span_attrs, "gen_ai.usage.output_tokens")
                )
                total_tok = (
                    _int_attr(span_attrs, "llm.usage.total_tokens")
                    or ((input_tok or 0) + (output_tok or 0) or None)
                )

                spans.append(
                    InferenceSpan(
                        team_id=team_id,
                        model_name=model_name[:255],
                        model_version=_str_attr(span_attrs, "model.version"),
                        serving_framework=_str_attr(span_attrs, "service.framework") or "custom",
                        cluster_name=_str_attr(resource_attrs, "cluster.name"),
                        request_id=(raw.get("spanId") or str(uuid4()))[:128],
                        trace_id=(raw.get("traceId") or None),
                        input_tokens=input_tok,
                        output_tokens=output_tok,
                        total_tokens=total_tok,
                        duration_ms=max(0.0, duration_ms),
                        started_at=started_at,
                        ended_at=ended_at,
                    )
                )

    return spans, errors


def _parse_heliox(payload: dict, team_id: UUID) -> tuple[list[InferenceSpan], list[str]]:
    """Parse Heliox simplified format into InferenceSpan objects."""
    spans: list[InferenceSpan] = []
    errors: list[str] = []

    for i, raw in enumerate(payload.get("spans", [])):
        try:
            s = HelioxSpan(**raw)
        except Exception as exc:
            errors.append(f"span[{i}]: validation error — {exc}")
            continue

        if not s.model_name:
            errors.append(f"span[{i}]: missing model_name; skipped")
            continue

        total = s.total_tokens or ((s.input_tokens or 0) + (s.output_tokens or 0)) or None

        spans.append(
            InferenceSpan(
                team_id=team_id,
                model_name=s.model_name,
                model_version=s.model_version,
                serving_framework=s.serving_framework,
                cluster_name=s.cluster_name,
                request_id=s.request_id,
                trace_id=s.trace_id,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                total_tokens=total,
                duration_ms=s.duration_ms,
                ttfb_ms=s.ttfb_ms,
                gpu_type=s.gpu_type,
                gpu_count=s.gpu_count,
                started_at=s.started_at,
                ended_at=s.ended_at or s.started_at,
            )
        )

    return spans, errors


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/spans",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest inference spans (OTel OTLP or Heliox simplified format)",
    description=(
        "Accepts OpenTelemetry OTLP JSON or Heliox simplified span format. "
        "Auto-detected by the presence of `resourceSpans` key. "
        "Max 1,000 spans per request. Triggers async cost attribution."
    ),
)
def ingest_spans(
    payload: dict,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id: UUID = get_effective_team_id(api_key)

    # Detect format
    if "resourceSpans" in payload:
        spans, errors = _parse_otlp(payload, team_id)
    elif "spans" in payload:
        spans, errors = _parse_heliox(payload, team_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Unrecognised payload format. "
                "Expected OTel OTLP (`resourceSpans` key) or "
                "Heliox simplified (`spans` key)."
            ),
        )

    # Hard limit
    if len(spans) > _MAX_SPANS_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Batch too large: {len(spans)} spans. "
                f"Maximum is {_MAX_SPANS_PER_REQUEST} spans per request. "
                "Split into smaller batches."
            ),
        )

    accepted = 0
    if spans:
        for span in spans:
            db.add(span)
        try:
            db.commit()
            accepted = len(spans)
        except Exception as exc:
            db.rollback()
            logger.error("ingest_spans: commit failed — %s", exc, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to persist spans.",
            )

        # Queue async cost attribution for this window
        if spans:
            try:
                min_started = min(s.started_at for s in spans)
                max_started = max(s.started_at for s in spans)
                from app.tasks.inference_tasks import attribute_inference_costs
                attribute_inference_costs.delay(
                    str(team_id),
                    min_started.isoformat(),
                    max_started.isoformat(),
                )
            except Exception as exc:
                # Non-fatal: attribution will be picked up by nightly task
                logger.warning("ingest_spans: could not enqueue attribution task — %s", exc)

    record_api_usage(db, team_id=team_id, endpoint="ingest_inference_spans")

    return {
        "accepted": accepted,
        "rejected": len(errors),
        "errors": errors[:20],  # cap error list
    }


@router.get(
    "/models",
    summary="List all tracked inference models",
)
def list_models(
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id: UUID = get_effective_team_id(api_key)

    rows = db.execute(
        select(
            InferenceSpan.model_name,
            InferenceSpan.serving_framework,
            InferenceSpan.cluster_name,
            func.max(InferenceSpan.started_at).label("last_seen"),
            func.count(InferenceSpan.id).label("total_requests"),
            func.avg(InferenceSpan.cost_per_1k_tokens).label("avg_cost_per_1k_tokens"),
        )
        .where(InferenceSpan.team_id == team_id)
        .group_by(
            InferenceSpan.model_name,
            InferenceSpan.serving_framework,
            InferenceSpan.cluster_name,
        )
        .order_by(func.max(InferenceSpan.started_at).desc())
    ).all()

    # Today's request count per model
    today = datetime.now(timezone.utc).date()
    today_counts: dict[str, int] = {}
    today_rows = db.execute(
        select(
            InferenceSpan.model_name,
            func.count(InferenceSpan.id).label("cnt"),
        )
        .where(
            InferenceSpan.team_id == team_id,
            func.date(InferenceSpan.started_at) == today,
        )
        .group_by(InferenceSpan.model_name)
    ).all()
    for r in today_rows:
        today_counts[r.model_name] = r.cnt

    return {
        "models": [
            {
                "model_name": r.model_name,
                "serving_framework": r.serving_framework,
                "cluster_name": r.cluster_name,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                "total_requests_today": today_counts.get(r.model_name, 0),
                "avg_cost_per_1k_tokens": (
                    round(float(r.avg_cost_per_1k_tokens), 6)
                    if r.avg_cost_per_1k_tokens else None
                ),
            }
            for r in rows
        ]
    }


@router.get(
    "/summary",
    summary="Cost-per-model time series",
)
def get_summary(
    model_name: Optional[str] = Query(default=None, description="Filter by model name"),
    days: int = Query(default=7, ge=1, le=365, description="Lookback window in days"),
    granularity: str = Query(default="day", description="Aggregation: hour | day | week"),
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id: UUID = get_effective_team_id(api_key)

    q = (
        select(
            ModelCostSummary.model_name,
            ModelCostSummary.date,
            ModelCostSummary.cluster_name,
            ModelCostSummary.request_count,
            ModelCostSummary.total_cost_usd,
            ModelCostSummary.avg_cost_per_request,
            ModelCostSummary.avg_cost_per_1k_tokens,
            ModelCostSummary.avg_duration_ms,
            ModelCostSummary.total_input_tokens,
            ModelCostSummary.total_output_tokens,
        )
        .where(
            ModelCostSummary.team_id == team_id,
            ModelCostSummary.date >= func.current_date() - days,
        )
        .order_by(ModelCostSummary.date)
    )
    if model_name:
        q = q.where(ModelCostSummary.model_name == model_name)

    rows = db.execute(q).all()

    return {
        "model_name": model_name,
        "days": days,
        "granularity": granularity,
        "series": [
            {
                "date": str(r.date),
                "model_name": r.model_name,
                "cluster_name": r.cluster_name,
                "request_count": r.request_count,
                "total_cost_usd": r.total_cost_usd,
                "avg_cost_per_request": r.avg_cost_per_request,
                "avg_cost_per_1k_tokens": r.avg_cost_per_1k_tokens,
                "avg_duration_ms": r.avg_duration_ms,
                "total_input_tokens": r.total_input_tokens,
                "total_output_tokens": r.total_output_tokens,
            }
            for r in rows
        ],
    }


@router.get(
    "/cost-per-request",
    summary="Cost distribution per request by model (p50/p95/p99)",
)
def cost_per_request(
    days: int = Query(default=7, ge=1, le=90, description="Lookback window in days"),
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
) -> Any:
    team_id: UUID = get_effective_team_id(api_key)

    rows = db.execute(
        select(
            ModelCostSummary.model_name,
            func.avg(ModelCostSummary.avg_cost_per_request).label("p50_cost"),
            func.avg(ModelCostSummary.p99_cost_per_request).label("p99_cost"),
            func.sum(ModelCostSummary.request_count).label("total_requests"),
            func.sum(ModelCostSummary.total_cost_usd).label("total_cost"),
            func.avg(ModelCostSummary.avg_cost_per_1k_tokens).label("avg_per_1k"),
        )
        .where(
            ModelCostSummary.team_id == team_id,
            ModelCostSummary.date >= func.current_date() - days,
        )
        .group_by(ModelCostSummary.model_name)
        .order_by(func.sum(ModelCostSummary.total_cost_usd).desc())
    ).all()

    return {
        "days": days,
        "models": [
            {
                "model_name": r.model_name,
                "p50_cost_per_request": round(float(r.p50_cost or 0), 6),
                "p99_cost_per_request": round(float(r.p99_cost or 0), 6) if r.p99_cost else None,
                "total_requests": r.total_requests or 0,
                "total_cost_usd": round(float(r.total_cost or 0), 4),
                "avg_cost_per_1k_tokens": (
                    round(float(r.avg_per_1k), 6) if r.avg_per_1k else None
                ),
            }
            for r in rows
        ],
    }
