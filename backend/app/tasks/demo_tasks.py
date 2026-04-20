"""Celery tasks for the demo environment.

The daily reset task runs at 3 AM UTC via Celery Beat so the demo never
accumulates stale prospect data.  It only runs when DEMO_MODE=True.
"""
from __future__ import annotations

import logging

from app.celery_app import celery_app
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.demo_tasks.reset_demo_environment", bind=True)
def reset_demo_environment(self):
    """Re-seed the demo tenant with fresh data.

    Idempotent — safe to call multiple times.  Skips gracefully when
    DEMO_MODE is disabled so the same task module can be imported in
    non-demo deployments without side effects.
    """
    settings = get_settings()
    if not settings.DEMO_MODE:
        logger.info("reset_demo_environment: DEMO_MODE=False, skipping.")
        return {"skipped": True, "reason": "DEMO_MODE is disabled"}

    logger.info("reset_demo_environment: starting daily demo reset")
    from datetime import datetime, timezone

    from app.core.db import SessionLocal
    from app.api.routes.demo import (
        _seed_demo_team_and_user,
        _clear_demo_data,
        _seed_costs,
        _seed_usage,
        _seed_budgets,
        _seed_recommendations,
    )
    from datetime import date

    db = SessionLocal()
    try:
        today = date.today()
        team, user, _ = _seed_demo_team_and_user(db)
        cleared = _clear_demo_data(db, team.id)
        cost_count = _seed_costs(db, team.id, today)
        usage_count = _seed_usage(db, team.id, today)
        budgets = _seed_budgets(db, team.id, today)
        recs = _seed_recommendations(db, team.id, user.id)
        db.commit()

        seeded_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "reset_demo_environment: complete — %d costs, %d usage, %d budgets, %d recs",
            cost_count, usage_count, budgets["policies"], recs,
        )
        return {
            "status": "reset_complete",
            "seeded_at": seeded_at,
            "demo_team_id": str(team.id),
            "cost_snapshots": cost_count,
            "usage_snapshots": usage_count,
            "budget_policies": budgets["policies"],
            "recommendations": recs,
            "cleared": cleared,
        }
    except Exception as exc:
        db.rollback()
        logger.error("reset_demo_environment: failed — %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=300, max_retries=2)
    finally:
        db.close()
