"""Celery application for async tasks and scheduled jobs."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

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
}

