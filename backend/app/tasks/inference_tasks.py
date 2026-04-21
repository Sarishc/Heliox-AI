"""Celery tasks for inference span cost attribution and daily rollups."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.services.inference_cost_attribution import (
    attribute_costs_for_window,
    rollup_daily_summaries,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="inference.attribute_costs",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def attribute_inference_costs(
    self,
    team_id: str,
    start_iso: str,
    end_iso: str,
    cluster_name: str | None = None,
) -> dict:
    """Run the cost attribution engine for a given time window.

    Enqueued by the /inference/spans ingest endpoint immediately after
    a batch of spans is committed.
    """
    from uuid import UUID

    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)

    db = SessionLocal()
    try:
        result = attribute_costs_for_window(
            db=db,
            team_id=UUID(team_id),
            start_time=start,
            end_time=end,
            cluster_name=cluster_name,
        )
        db.commit()
        logger.info(
            "inference.attribute_costs: team=%s window=[%s, %s] " "attributed=%d skipped=%d errors=%d",
            team_id,
            start_iso,
            end_iso,
            result.spans_attributed,
            result.spans_skipped,
            len(result.errors),
        )
        return {
            "spans_attributed": result.spans_attributed,
            "spans_skipped": result.spans_skipped,
            "windows_processed": result.windows_processed,
            "errors": result.errors,
        }
    except Exception as exc:
        db.rollback()
        logger.error("inference.attribute_costs failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name="inference.daily_rollup",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def inference_daily_rollup(self, rollup_date_iso: str | None = None) -> dict:
    """Nightly task — roll up previous day's spans into ModelCostSummary.

    Runs for all teams that have InferenceSpan rows for the target date.
    Scheduled at 01:30 UTC daily (after attribute_costs window closes).
    """
    from app.models.inference import InferenceSpan
    from sqlalchemy import func, select

    target_date: date = (
        date.fromisoformat(rollup_date_iso)
        if rollup_date_iso
        else (datetime.now(timezone.utc) - timedelta(days=1)).date()
    )

    db = SessionLocal()
    try:
        # Find all teams with spans on this date
        team_ids = (
            db.execute(
                select(InferenceSpan.team_id).where(func.date(InferenceSpan.started_at) == target_date).distinct()
            )
            .scalars()
            .all()
        )

        written_total = 0
        for team_id in team_ids:
            written = rollup_daily_summaries(db=db, team_id=team_id, rollup_date=target_date)
            written_total += written

        db.commit()
        logger.info(
            "inference.daily_rollup: date=%s teams=%d summaries_written=%d",
            target_date,
            len(team_ids),
            written_total,
        )
        return {
            "date": str(target_date),
            "teams_processed": len(team_ids),
            "summaries_written": written_total,
        }
    except Exception as exc:
        db.rollback()
        logger.error("inference.daily_rollup failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
    finally:
        db.close()
