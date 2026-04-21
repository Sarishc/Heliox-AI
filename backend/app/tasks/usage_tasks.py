"""Celery tasks for usage metering and billing."""

import logging
from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy import func

from app.celery_app import celery_app
from app.core.db import get_db
from app.models.usage import UsageEvent, UsageDailyRollup
from app.models.team import Team
from app.models.team_member import TeamMember
from app.utils.usage_metering import record_seat_snapshot
from app.services.stripe_metering import export_usage_to_stripe

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.usage_tasks.rollup_daily_usage")
def rollup_daily_usage(date_str: str = None) -> Dict:
    """
    Roll up usage events into daily aggregates.

    This task:
    1. Aggregates usage_events for a specific date
    2. Upserts into usage_daily_rollups
    3. Can be run for historical dates or defaults to yesterday

    Args:
        date_str: Date to rollup (YYYY-MM-DD), defaults to yesterday

    Returns:
        Dictionary with rollup statistics
    """
    db = next(get_db())

    try:
        # Determine date to rollup
        if date_str:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            # Default to yesterday (gives a full day of data)
            target_date = (datetime.utcnow() - timedelta(days=1)).date()

        logger.info(f"Starting daily usage rollup for {target_date}")

        # Define date range for rollup (full UTC day)
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date, datetime.max.time())

        # Aggregate usage events by team and event type
        rollup_query = (
            db.query(
                UsageEvent.team_id,
                UsageEvent.event_type,
                func.sum(UsageEvent.quantity).label("total_quantity"),
            )
            .filter(
                UsageEvent.created_at >= start_datetime,
                UsageEvent.created_at <= end_datetime,
            )
            .group_by(UsageEvent.team_id, UsageEvent.event_type)
            .all()
        )

        rollups_created = 0
        rollups_updated = 0

        for row in rollup_query:
            team_id = row.team_id
            event_type = row.event_type
            total_quantity = int(row.total_quantity) if row.total_quantity else 0

            # Upsert daily rollup
            existing_rollup = (
                db.query(UsageDailyRollup)
                .filter(
                    UsageDailyRollup.team_id == team_id,
                    UsageDailyRollup.date == target_date,
                    UsageDailyRollup.event_type == event_type,
                )
                .first()
            )

            if existing_rollup:
                # Update existing rollup
                existing_rollup.total_quantity = total_quantity
                existing_rollup.updated_at = datetime.utcnow()
                rollups_updated += 1
            else:
                # Create new rollup
                rollup = UsageDailyRollup(
                    team_id=team_id,
                    date=target_date,
                    event_type=event_type,
                    total_quantity=total_quantity,
                )
                db.add(rollup)
                rollups_created += 1

        db.commit()

        logger.info(
            f"Daily usage rollup completed for {target_date}: " f"{rollups_created} created, {rollups_updated} updated"
        )

        return {
            "date": target_date.isoformat(),
            "rollups_created": rollups_created,
            "rollups_updated": rollups_updated,
            "total_rollups": rollups_created + rollups_updated,
        }

    except Exception as e:
        logger.error(f"Daily usage rollup failed: {e}", exc_info=True)
        db.rollback()
        raise

    finally:
        db.close()


@celery_app.task(name="app.tasks.usage_tasks.cleanup_old_usage_events")
def cleanup_old_usage_events(retention_days: int = 30) -> Dict:
    """
    Clean up old usage events based on retention policy.

    Deletes usage_events older than retention_days.
    Daily rollups are preserved (12 month retention handled separately).

    Args:
        retention_days: Number of days to retain raw events (default: 30)

    Returns:
        Dictionary with cleanup statistics
    """
    db = next(get_db())

    try:
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

        logger.info(f"Starting cleanup of usage events older than {cutoff_date}")

        # Delete old events
        deleted_count = (
            db.query(UsageEvent).filter(UsageEvent.created_at < cutoff_date).delete(synchronize_session=False)
        )

        db.commit()

        logger.info(f"Cleanup completed: deleted {deleted_count} usage events")

        return {
            "cutoff_date": cutoff_date.isoformat(),
            "retention_days": retention_days,
            "deleted_count": deleted_count,
        }

    except Exception as e:
        logger.error(f"Usage events cleanup failed: {e}", exc_info=True)
        db.rollback()
        raise

    finally:
        db.close()


@celery_app.task(name="app.tasks.usage_tasks.cleanup_old_daily_rollups")
def cleanup_old_daily_rollups(retention_months: int = 12) -> Dict:
    """
    Clean up old daily rollups based on retention policy.

    Deletes usage_daily_rollups older than retention_months.

    Args:
        retention_months: Number of months to retain rollups (default: 12)

    Returns:
        Dictionary with cleanup statistics
    """
    db = next(get_db())

    try:
        # Calculate cutoff date (in months)
        retention_days = retention_months * 30  # Approximate
        cutoff_date = (datetime.utcnow() - timedelta(days=retention_days)).date()

        logger.info(f"Starting cleanup of daily rollups older than {cutoff_date}")

        # Delete old rollups
        deleted_count = (
            db.query(UsageDailyRollup).filter(UsageDailyRollup.date < cutoff_date).delete(synchronize_session=False)
        )

        db.commit()

        logger.info(f"Cleanup completed: deleted {deleted_count} daily rollups")

        return {
            "cutoff_date": cutoff_date.isoformat(),
            "retention_months": retention_months,
            "deleted_count": deleted_count,
        }

    except Exception as e:
        logger.error(f"Daily rollups cleanup failed: {e}", exc_info=True)
        db.rollback()
        raise

    finally:
        db.close()


@celery_app.task(name="app.tasks.usage_tasks.snapshot_daily_seats")
def snapshot_daily_seats() -> Dict:
    """
    Take a daily snapshot of active seats per team.

    Counts active team members and records as usage events.
    Run daily to track seat usage for billing.

    Returns:
        Dictionary with snapshot statistics
    """
    db = next(get_db())

    try:
        logger.info("Starting daily seats snapshot")

        # Query all teams with their active member counts
        team_seats = (
            db.query(Team.id.label("team_id"), func.count(TeamMember.id).label("seat_count"))
            .outerjoin(TeamMember, Team.id == TeamMember.team_id)
            .group_by(Team.id)
            .all()
        )

        teams_processed = 0
        total_seats = 0

        for row in team_seats:
            team_id = row.team_id
            seat_count = int(row.seat_count) if row.seat_count else 0

            # Record seat snapshot
            record_seat_snapshot(team_id=team_id, active_users_count=seat_count, db=db)

            teams_processed += 1
            total_seats += seat_count

        logger.info(f"Daily seats snapshot completed: {teams_processed} teams, " f"{total_seats} total seats")

        return {
            "snapshot_date": datetime.utcnow().date().isoformat(),
            "teams_processed": teams_processed,
            "total_seats": total_seats,
        }

    except Exception as e:
        logger.error(f"Daily seats snapshot failed: {e}", exc_info=True)
        raise

    finally:
        db.close()


@celery_app.task(name="app.tasks.usage_tasks.export_stripe_metering")
def export_stripe_metering_task(date_str: str = None) -> Dict:
    """
    Export usage rollups to Stripe Billing Meter Events for usage-based billing.

    Runs after usage rollup and seat snapshot (schedule ~03:30 UTC).
    Idempotent: skips already-successful exports; retries failed ones.

    Args:
        date_str: Date to export (YYYY-MM-DD), defaults to yesterday.

    Returns:
        {exported, skipped, failed, errors}
    """
    db = next(get_db())
    try:
        if date_str:
            export_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            export_date = (datetime.utcnow() - timedelta(days=1)).date()

        logger.info(f"Starting Stripe metering export for {export_date}")
        result = export_usage_to_stripe(db, export_date, dry_run=False)
        logger.info(
            f"Stripe metering export completed for {export_date}: "
            f"exported={result['exported']}, skipped={result['skipped']}, failed={result['failed']}"
        )
        return result
    except Exception as e:
        logger.error(f"Stripe metering export failed: {e}", exc_info=True)
        raise
    finally:
        db.close()
