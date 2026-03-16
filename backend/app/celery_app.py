"""Celery application for async tasks and scheduled jobs."""
from celery import Celery, signals
from celery.schedules import crontab

from app.core.config import get_settings

# Initialize Sentry when worker starts (must run before tasks are loaded)
@signals.worker_init.connect
def _init_sentry_on_worker(**kwargs):
    from app.core.observability import init_sentry_celery
    init_sentry_celery()

# Import all task modules so Beat schedule and workers can resolve task names
import app.tasks.budget_tasks  # noqa: F401
import app.tasks.integration_tasks  # noqa: F401
import app.tasks.rollup_tasks  # noqa: F401
import app.tasks.slack_tasks  # noqa: F401
import app.tasks.usage_tasks  # noqa: F401

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "heliox",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.TIMEZONE or "UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
    task_soft_time_limit=240,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule_filename='/app/data/celerybeat-schedule.db',  # Fix permission error
)

# Celery Beat schedule
celery_app.conf.beat_schedule = {
    # Daily summary at 9 AM local time
    "daily-summary": {
        "task": "app.tasks.slack_tasks.send_daily_summary_task",
        "schedule": crontab(
            hour=settings.DAILY_SUMMARY_HOUR or 9,
            minute=0
        ),
    },
    # Check burn rate every hour (8 AM - 8 PM)
    "check-burn-rate": {
        "task": "app.tasks.slack_tasks.check_burn_rate_task",
        "schedule": crontab(
            hour="8-20",
            minute=0
        ),
    },
    # Check idle spend twice daily (10 AM, 4 PM)
    "check-idle-spend": {
        "task": "app.tasks.slack_tasks.check_idle_spend_task",
        "schedule": crontab(
            hour="10,16",
            minute=0
        ),
    },
    # Check anomalies every 6 hours
    "check-anomalies": {
        "task": "app.tasks.slack_tasks.check_anomalies_task",
        "schedule": crontab(hour="*/6", minute=15),
    },
    "budget-guardrails": {
        "task": "app.tasks.budget_tasks.budget_guardrails_tick",
        "schedule": crontab(hour="*", minute=5),
    },
    # Daily rollups at 1 AM
    "daily-rollups": {
        "task": "app.tasks.rollup_tasks.compute_daily_rollups",
        "schedule": crontab(
            hour=1,
            minute=0
        ),
    },
    # Integration syncs every 5 minutes
    "integration-syncs": {
        "task": "app.tasks.integration_tasks.run_scheduled_syncs",
        "schedule": crontab(minute="*/5"),
    },
    # Usage metering: Daily rollup at 02:00 UTC
    "usage-daily-rollup": {
        "task": "app.tasks.usage_tasks.rollup_daily_usage",
        "schedule": crontab(hour=2, minute=0),
    },
    # Usage metering: Daily seats snapshot at 03:00 UTC
    "usage-seats-snapshot": {
        "task": "app.tasks.usage_tasks.snapshot_daily_seats",
        "schedule": crontab(hour=3, minute=0),
    },
    # Usage retention: Cleanup old events weekly (Sunday 04:00 UTC)
    "usage-cleanup-events": {
        "task": "app.tasks.usage_tasks.cleanup_old_usage_events",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
    },
    # Usage retention: Cleanup old rollups monthly (1st of month, 05:00 UTC)
    "usage-cleanup-rollups": {
        "task": "app.tasks.usage_tasks.cleanup_old_daily_rollups",
        "schedule": crontab(hour=5, minute=0, day_of_month=1),
    },
}

