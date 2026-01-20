"""Celery tasks for rollups."""
import logging
from datetime import date, timedelta

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.models.team import Team
from app.services.rollups import compute_daily_rollup

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.rollup_tasks.compute_daily_rollups",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def compute_daily_rollups(self, date_str: str | None = None):
    """
    Compute daily rollups for all teams.
    """
    db = SessionLocal()
    try:
        target_date = date.fromisoformat(date_str) if date_str else date.today() - timedelta(days=1)
        teams = db.query(Team).all()
        for team in teams:
            compute_daily_rollup(db, team_id=team.id, target_date=target_date)
        return {"status": "ok", "teams": len(teams), "date": str(target_date)}
    except Exception as exc:
        logger.error(f"Daily rollup task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
    finally:
        db.close()
