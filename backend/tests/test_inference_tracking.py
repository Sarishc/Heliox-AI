"""Tests for per-request inference cost attribution and rollup."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.models.cost import CostSnapshot
from app.models.inference import InferenceSpan, ModelCostSummary
from app.models.team import Team
from app.services.inference_cost_attribution import (
    attribute_costs_for_window,
    rollup_daily_summaries,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_team(db, name="Test Team"):
    t = Team(name=name)
    db.add(t)
    db.flush()
    return t


def _make_span(
    db,
    team_id,
    model_name="llama-3-70b",
    duration_ms=1000.0,
    started_at=None,
    cluster_name="gpu-prod",
    input_tokens=512,
    output_tokens=256,
    cost_usd=None,
):
    now = started_at or datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
    span = InferenceSpan(
        team_id=team_id,
        model_name=model_name,
        serving_framework="vllm",
        cluster_name=cluster_name,
        request_id=f"req-{model_name}-{duration_ms}",
        duration_ms=duration_ms,
        started_at=now,
        ended_at=now + timedelta(milliseconds=duration_ms),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=(input_tokens or 0) + (output_tokens or 0),
        cost_usd=cost_usd,
    )
    db.add(span)
    db.flush()
    return span


def _make_cost_snapshot(db, team_id, cost_usd=100.0, day=None, provider="gpu-prod"):
    d = day or date(2026, 4, 1)
    snap = CostSnapshot(
        team_id=team_id,
        date=d,
        provider=provider,
        gpu_type="a100",
        cost_usd=Decimal(str(cost_usd)),
    )
    db.add(snap)
    db.flush()
    return snap


# ── attribution engine ────────────────────────────────────────────────────────

def test_attribute_costs_proportional_by_duration(db_session):
    """Costs split proportionally: 2x duration → 2x cost."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)

    _make_cost_snapshot(db_session, team.id, cost_usd=300.0, day=day)
    span_a = _make_span(db_session, team.id, duration_ms=2000.0, started_at=start)
    span_b = _make_span(db_session, team.id, model_name="sd-xl", duration_ms=1000.0, started_at=start)

    result = attribute_costs_for_window(db_session, team.id, start, end)

    assert result.spans_attributed == 2
    assert result.spans_skipped == 0
    assert span_a.cost_usd is not None
    assert span_b.cost_usd is not None
    # span_a got 2/3 of $300 = $200; span_b got 1/3 = $100
    assert abs(span_a.cost_usd - 200.0) < 0.01
    assert abs(span_b.cost_usd - 100.0) < 0.01


def test_attribute_costs_sets_cost_per_1k_tokens(db_session):
    """cost_per_1k_tokens is computed when token counts are present."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)

    _make_cost_snapshot(db_session, team.id, cost_usd=100.0, day=day)
    span = _make_span(
        db_session, team.id,
        duration_ms=1000.0, started_at=start,
        input_tokens=500, output_tokens=500,
    )

    attribute_costs_for_window(db_session, team.id, start, end)

    assert span.cost_usd is not None
    assert span.cost_per_1k_tokens is not None
    # cost_per_1k = (100.0 / 1000) * 1000 = $100.00
    assert abs(span.cost_per_1k_tokens - 100.0) < 0.01


def test_attribute_costs_skips_zero_duration(db_session):
    """Spans with duration_ms=0 are skipped."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc)

    _make_cost_snapshot(db_session, team.id, cost_usd=100.0, day=day)
    span = InferenceSpan(
        team_id=team.id,
        model_name="llama-3-70b",
        serving_framework="vllm",
        cluster_name="gpu-prod",
        request_id="req-zero",
        duration_ms=0.0,
        started_at=start,
        ended_at=start,
    )
    db_session.add(span)
    db_session.flush()

    result = attribute_costs_for_window(db_session, team.id, start, end)

    assert result.spans_skipped == 1
    assert span.cost_usd is None


def test_attribute_costs_no_spans_returns_empty(db_session):
    """Returns empty result when there are no uncosted spans."""
    team = _make_team(db_session)
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, tzinfo=timezone.utc)

    result = attribute_costs_for_window(db_session, team.id, start, end)

    assert result.spans_attributed == 0
    assert result.spans_skipped == 0
    assert result.windows_processed == 0


def test_attribute_costs_no_cost_data_skips_spans(db_session):
    """Spans with no matching GPU cost data are skipped (not errored)."""
    team = _make_team(db_session)
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, tzinfo=timezone.utc)

    span = _make_span(db_session, team.id, started_at=start)
    result = attribute_costs_for_window(db_session, team.id, start, end)

    assert result.spans_attributed == 0
    assert result.spans_skipped == 1
    assert span.cost_usd is None


def test_attribute_costs_already_costed_ignored(db_session):
    """Spans with cost_usd already set are not re-attributed."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, tzinfo=timezone.utc)

    _make_cost_snapshot(db_session, team.id, cost_usd=100.0, day=day)
    span = _make_span(db_session, team.id, started_at=start, cost_usd=0.5)

    result = attribute_costs_for_window(db_session, team.id, start, end)

    # Already costed → no uncosted spans → nothing to do
    assert result.spans_attributed == 0
    assert span.cost_usd == 0.5  # unchanged


def test_attribute_costs_cluster_filter(db_session):
    """cluster_name filter restricts attribution to the given cluster."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 2, tzinfo=timezone.utc)

    _make_cost_snapshot(db_session, team.id, cost_usd=100.0, day=day, provider="cluster-a")
    span_a = _make_span(db_session, team.id, started_at=start, cluster_name="cluster-a")
    span_b = _make_span(
        db_session, team.id,
        model_name="sd-xl",
        started_at=start,
        cluster_name="cluster-b",
    )

    result = attribute_costs_for_window(
        db_session, team.id, start, end, cluster_name="cluster-a"
    )

    assert result.spans_attributed == 1
    assert span_a.cost_usd is not None
    assert span_b.cost_usd is None


# ── daily rollup ──────────────────────────────────────────────────────────────

def test_rollup_creates_model_cost_summary(db_session):
    """rollup_daily_summaries writes one ModelCostSummary per (model, cluster, day)."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)

    for _ in range(3):
        span = _make_span(db_session, team.id, started_at=t, cost_usd=10.0)

    written = rollup_daily_summaries(db_session, team.id, day)
    assert written >= 1

    summary = db_session.query(ModelCostSummary).filter_by(
        team_id=team.id, model_name="llama-3-70b", date=day
    ).first()
    assert summary is not None
    assert summary.request_count == 3
    assert abs(summary.total_cost_usd - 30.0) < 0.001


def test_rollup_no_spans_returns_zero(db_session):
    """rollup_daily_summaries returns 0 when there are no spans."""
    team = _make_team(db_session)
    written = rollup_daily_summaries(db_session, team.id, date(2026, 4, 1))
    assert written == 0


def test_rollup_groups_by_model(db_session):
    """Separate models get separate summary rows."""
    team = _make_team(db_session)
    day = date(2026, 4, 1)
    t = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)

    _make_span(db_session, team.id, model_name="llama-3-70b", started_at=t, cost_usd=20.0)
    _make_span(db_session, team.id, model_name="stable-diffusion-xl", started_at=t, cost_usd=15.0)

    written = rollup_daily_summaries(db_session, team.id, day)
    assert written == 2


# ── OTLP parsing (unit) ───────────────────────────────────────────────────────

def test_parse_otlp_extracts_model_and_tokens():
    """_parse_otlp correctly maps OTel attributes to InferenceSpan fields."""
    from uuid import uuid4
    from app.api.routes.inference import _parse_otlp

    team_id = uuid4()
    start_ns = 1_700_000_000_000_000_000  # Unix ns
    end_ns = start_ns + 1_234_000_000     # +1.234s

    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": [
                    {"key": "service.name", "value": {"stringValue": "my-vllm"}},
                ]},
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "spanId": "abc123",
                                "traceId": "trace456",
                                "startTimeUnixNano": str(start_ns),
                                "endTimeUnixNano": str(end_ns),
                                "attributes": [
                                    {"key": "llm.model_name", "value": {"stringValue": "llama-3-70b"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "512"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "256"}},
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }

    spans, errors = _parse_otlp(payload, team_id)
    assert len(spans) == 1
    assert len(errors) == 0
    span = spans[0]
    assert span.model_name == "llama-3-70b"
    assert span.input_tokens == 512
    assert span.output_tokens == 256
    assert abs(span.duration_ms - 1234.0) < 1.0
    assert span.request_id == "abc123"


def test_parse_heliox_simplified_format():
    """_parse_heliox creates InferenceSpan from simplified dict."""
    from uuid import uuid4
    from app.api.routes.inference import _parse_heliox

    team_id = uuid4()
    payload = {
        "spans": [
            {
                "model_name": "stable-diffusion-xl",
                "request_id": "req-001",
                "duration_ms": 2500.0,
                "started_at": "2026-04-01T12:00:00Z",
                "ended_at": "2026-04-01T12:00:02.5Z",
                "serving_framework": "custom",
                "cluster_name": "ml-cluster",
                "input_tokens": None,
                "output_tokens": None,
            }
        ]
    }

    spans, errors = _parse_heliox(payload, team_id)
    assert len(spans) == 1
    assert len(errors) == 0
    assert spans[0].model_name == "stable-diffusion-xl"
    assert spans[0].duration_ms == 2500.0
    assert spans[0].cluster_name == "ml-cluster"
