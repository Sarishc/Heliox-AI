"""Cost attribution engine for per-inference request cost computation.

Attribution logic:
    span_cost = (span_duration_ms / total_cluster_duration_ms_in_window)
                * cluster_cost_in_window

When token counts are available:
    cost_per_1k_tokens = (span_cost / total_tokens) * 1000
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.cost import CostSnapshot
from app.models.inference import InferenceSpan, ModelCostSummary

logger = logging.getLogger(__name__)


@dataclass
class AttributionResult:
    spans_attributed: int = 0
    spans_skipped: int = 0
    windows_processed: int = 0
    errors: list[str] = field(default_factory=list)


def attribute_costs_for_window(
    db: Session,
    team_id: UUID,
    start_time: datetime,
    end_time: datetime,
    cluster_name: Optional[str] = None,
) -> AttributionResult:
    """Attribute GPU costs to inference spans within a time window.

    Fetches uncosted InferenceSpan records, matches them to CostSnapshot
    data for the same cluster/day, and writes cost_usd back.
    """
    result = AttributionResult()

    # ── 1. Find uncosted spans in window ─────────────────────────────────────
    span_q = (
        select(InferenceSpan)
        .where(
            InferenceSpan.team_id == team_id,
            InferenceSpan.started_at >= start_time,
            InferenceSpan.started_at < end_time,
            InferenceSpan.cost_usd.is_(None),
        )
    )
    if cluster_name:
        span_q = span_q.where(InferenceSpan.cluster_name == cluster_name)

    spans: list[InferenceSpan] = list(db.execute(span_q).scalars())
    if not spans:
        logger.debug(
            "attribution: no uncosted spans for team=%s window=[%s, %s]",
            team_id, start_time.isoformat(), end_time.isoformat(),
        )
        return result

    # ── 2. Group spans by (cluster_name, day) ─────────────────────────────────
    # For each (cluster, day) pair we need one CostSnapshot lookup.
    from collections import defaultdict
    cluster_day_spans: dict[tuple[str | None, date], list[InferenceSpan]] = defaultdict(list)
    for span in spans:
        day = span.started_at.date()
        cluster_day_spans[(span.cluster_name, day)].append(span)

    # ── 3. For each (cluster, day) compute costs ──────────────────────────────
    for (c_name, day), day_spans in cluster_day_spans.items():
        result.windows_processed += 1

        # Sum of all GPU costs for this cluster on this day
        cost_q = select(func.sum(CostSnapshot.cost_usd)).where(
            CostSnapshot.team_id == team_id,
            CostSnapshot.date == day,
        )
        if c_name:
            cost_q = cost_q.where(CostSnapshot.provider == c_name)

        cluster_cost = db.execute(cost_q).scalar_one_or_none()
        if not cluster_cost or float(cluster_cost) == 0:
            logger.info(
                "attribution: no GPU cost data for team=%s cluster=%s day=%s; skipping",
                team_id, c_name, day,
            )
            result.spans_skipped += len(day_spans)
            continue

        cluster_cost_f = float(cluster_cost)

        # Total duration across all spans on this day for this cluster
        total_duration_ms = sum(s.duration_ms for s in day_spans if s.duration_ms > 0)
        if total_duration_ms == 0:
            result.spans_skipped += len(day_spans)
            continue

        # ── 4. Write costs back ───────────────────────────────────────────────
        for span in day_spans:
            if span.duration_ms <= 0:
                result.spans_skipped += 1
                continue

            share = span.duration_ms / total_duration_ms
            cost = cluster_cost_f * share
            span.cost_usd = round(cost, 8)

            total_tokens = span.total_tokens or (
                (span.input_tokens or 0) + (span.output_tokens or 0)
            )
            if total_tokens and total_tokens > 0:
                span.cost_per_1k_tokens = round((cost / total_tokens) * 1000, 8)
                span.total_tokens = total_tokens

            result.spans_attributed += 1

    try:
        db.flush()
    except Exception as exc:
        logger.error("attribution: flush failed — %s", exc, exc_info=True)
        result.errors.append(str(exc))
        db.rollback()
        return result

    # Check for per-model cost spikes (cost_per_1k_tokens > 2x 7-day average)
    _maybe_publish_inference_alerts(db, team_id, spans)

    return result


def _maybe_publish_inference_alerts(
    db: Session,
    team_id: UUID,
    spans: list[InferenceSpan],
) -> None:
    """Publish INFERENCE_ALERT events for models whose cost_per_1k_tokens is 2x baseline."""
    from datetime import timedelta

    try:
        from app.core.events import EventType, HelioxEvent, publish_event_sync

        # Group newly-costed spans by model
        costed = [s for s in spans if s.cost_per_1k_tokens is not None]
        if not costed:
            return

        from collections import defaultdict
        by_model: dict[str, list[float]] = defaultdict(list)
        for s in costed:
            if s.cost_per_1k_tokens:
                by_model[s.model_name].append(s.cost_per_1k_tokens)

        seven_days_ago = min(s.started_at for s in costed) - timedelta(days=7)

        for model_name, current_costs in by_model.items():
            avg_current = sum(current_costs) / len(current_costs)

            # 7-day baseline from ModelCostSummary (cheapest historical average)
            baseline_row = db.execute(
                select(func.avg(ModelCostSummary.avg_cost_per_1k_tokens)).where(
                    ModelCostSummary.team_id == team_id,
                    ModelCostSummary.model_name == model_name,
                    ModelCostSummary.date >= seven_days_ago.date(),
                    ModelCostSummary.avg_cost_per_1k_tokens.isnot(None),
                )
            ).scalar_one_or_none()

            if not baseline_row or float(baseline_row) == 0:
                continue

            baseline = float(baseline_row)
            if avg_current > baseline * 2.0:
                publish_event_sync(
                    str(team_id),
                    HelioxEvent(
                        event_type=EventType.INFERENCE_ALERT,
                        team_id=str(team_id),
                        payload={
                            "model_name": model_name,
                            "avg_cost_per_1k_tokens": round(avg_current, 6),
                            "baseline_cost_per_1k_tokens": round(baseline, 6),
                            "multiple": round(avg_current / baseline, 2),
                            "message": (
                                f"{model_name} cost/1k tokens is "
                                f"{avg_current/baseline:.1f}x above 7-day baseline."
                            ),
                        },
                    ),
                )
    except Exception as exc:
        logger.debug("inference attribution: SSE alert skipped — %s", exc)


def rollup_daily_summaries(
    db: Session,
    team_id: UUID,
    rollup_date: date,
) -> int:
    """Aggregate InferenceSpan rows for one day into ModelCostSummary.

    Returns the number of summary rows written/updated.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    # Fetch all costed spans for the day
    spans_q = select(InferenceSpan).where(
        InferenceSpan.team_id == team_id,
        func.date(InferenceSpan.started_at) == rollup_date,
    )
    spans: list[InferenceSpan] = list(db.execute(spans_q).scalars())

    if not spans:
        return 0

    # Group by (model_name, serving_framework, cluster_name)
    from collections import defaultdict
    groups: dict[tuple[str, str, str | None], list[InferenceSpan]] = defaultdict(list)
    for s in spans:
        groups[(s.model_name, s.serving_framework, s.cluster_name)].append(s)

    written = 0
    for (model_name, framework, cluster), group_spans in groups.items():
        costed = [s for s in group_spans if s.cost_usd is not None]
        costs = [s.cost_usd for s in costed]  # type: ignore[misc]
        durations = [s.duration_ms for s in group_spans]
        token_costs_per_1k = [
            s.cost_per_1k_tokens for s in costed if s.cost_per_1k_tokens is not None
        ]

        total_cost = sum(costs) if costs else 0.0
        avg_cost = total_cost / len(costed) if costed else 0.0
        avg_dur = sum(durations) / len(durations) if durations else 0.0

        # p99 — sort and pick 99th percentile index
        def _p99(values: list[float]) -> Optional[float]:
            if not values:
                return None
            s_vals = sorted(values)
            idx = max(0, int(len(s_vals) * 0.99) - 1)
            return s_vals[idx]

        p99_cost = _p99(costs) if costs else None
        p99_dur = _p99(durations)
        avg_1k = sum(token_costs_per_1k) / len(token_costs_per_1k) if token_costs_per_1k else None

        total_in = sum(s.input_tokens or 0 for s in group_spans)
        total_out = sum(s.output_tokens or 0 for s in group_spans)

        values = {
            "team_id": team_id,
            "model_name": model_name,
            "serving_framework": framework,
            "cluster_name": cluster,
            "date": rollup_date,
            "request_count": len(group_spans),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_cost_usd": total_cost,
            "avg_cost_per_request": avg_cost,
            "avg_cost_per_1k_tokens": avg_1k,
            "p99_cost_per_request": p99_cost,
            "avg_duration_ms": avg_dur,
            "p99_duration_ms": p99_dur,
            "error_count": 0,
        }

        try:
            stmt = pg_insert(ModelCostSummary).values(**values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_model_cost_summary_team_model_cluster_date",
                set_={
                    k: v for k, v in values.items()
                    if k not in ("team_id", "model_name", "cluster_name", "date")
                },
            )
            db.execute(stmt)
            written += 1
        except Exception:
            # SQLite fallback for tests (no pg_insert support)
            existing = db.execute(
                select(ModelCostSummary).where(
                    ModelCostSummary.team_id == team_id,
                    ModelCostSummary.model_name == model_name,
                    ModelCostSummary.cluster_name == cluster,
                    ModelCostSummary.date == rollup_date,
                )
            ).scalar_one_or_none()
            if existing:
                for k, v in values.items():
                    if k not in ("team_id", "model_name", "cluster_name", "date"):
                        setattr(existing, k, v)
            else:
                db.add(ModelCostSummary(**values))
            written += 1

    try:
        db.flush()
    except Exception as exc:
        logger.error("rollup: flush failed — %s", exc, exc_info=True)
        db.rollback()
        return 0

    logger.info(
        "rollup: wrote %d summaries for team=%s date=%s", written, team_id, rollup_date
    )
    return written
