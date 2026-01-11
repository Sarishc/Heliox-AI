"""Celery tasks for Slack notifications."""
import asyncio
import logging
from typing import Optional

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.services.slack_notifications import (
    check_and_send_burn_rate_alert,
    check_and_send_idle_spend_alert,
    send_daily_summary_report
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.slack_tasks.check_burn_rate_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300  # 5 minutes
)
def check_burn_rate_task(self, date_str: Optional[str] = None):
    """
    Celery task to check burn rate and send alert if threshold exceeded.
    
    Args:
        date_str: Date to check (YYYY-MM-DD). Defaults to yesterday.
    """
    logger.info(f"Starting burn rate check task for date: {date_str or 'yesterday'}")
    
    db = SessionLocal()
    try:
        # Run async function in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        alert_sent = loop.run_until_complete(
            check_and_send_burn_rate_alert(db, date_str)
        )
        
        if alert_sent:
            logger.info("Burn rate alert sent successfully")
        else:
            logger.info("No burn rate alert needed")
        
        return {"alert_sent": alert_sent, "date": date_str}
        
    except Exception as e:
        logger.error(f"Burn rate check task failed: {e}", exc_info=True)
        # Retry the task
        raise self.retry(exc=e)
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.slack_tasks.check_idle_spend_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300  # 5 minutes
)
def check_idle_spend_task(self):
    """
    Celery task to check for idle spend and send alert if high-severity issues found.
    """
    logger.info("Starting idle spend check task")
    
    db = SessionLocal()
    try:
        # Run async function in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        alert_sent = loop.run_until_complete(
            check_and_send_idle_spend_alert(db)
        )
        
        if alert_sent:
            logger.info("Idle spend alert sent successfully")
        else:
            logger.info("No idle spend alert needed")
        
        return {"alert_sent": alert_sent}
        
    except Exception as e:
        logger.error(f"Idle spend check task failed: {e}", exc_info=True)
        # Retry the task
        raise self.retry(exc=e)
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.slack_tasks.send_daily_summary_task",
    bind=True,
    max_retries=3,
    default_retry_delay=600  # 10 minutes
)
def send_daily_summary_task(self):
    """
    Celery task to send daily summary report.
    """
    logger.info("Starting daily summary task")
    
    db = SessionLocal()
    try:
        # Run async function in sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        sent = loop.run_until_complete(
            send_daily_summary_report(db)
        )
        
        if sent:
            logger.info("Daily summary sent successfully")
        else:
            logger.info("Daily summary not sent (webhook not configured)")
        
        return {"sent": sent}
        
    except Exception as e:
        logger.error(f"Daily summary task failed: {e}", exc_info=True)
        # Retry the task
        raise self.retry(exc=e)
    finally:
        db.close()

