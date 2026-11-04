"""
Celery tasks for the shadow cost ledger. Registered only when LEDGER_SHADOW_WORKER_ENABLED is set.

Nothing schedules or enqueues these: they are not in the Beat schedule and existing integration tasks
never call them. Delivery is at-least-once; correctness comes from run, attempt and lease rows in the
database, so a repeated or late delivery is harmless.
"""

import logging
import random
from uuid import UUID

from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.services.ledger_shadow.activation import ShadowActivationRefused, ShadowPolicy
from app.services.ledger_shadow.orchestrator import ShadowSyncOrchestrator
from app.services.ledger_shadow.recovery import reap_abandoned_runs as reap

logger = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 900
MAX_DELIVERY_RETRIES = 5


def backoff_seconds(retries: int) -> int:
    """Bounded exponential backoff with jitter."""
    ceiling = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * 2**retries)
    return random.randint(BACKOFF_BASE_SECONDS // 2, ceiling)


@celery_app.task(
    bind=True,
    name="ledger.shadow_sync",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=MAX_DELIVERY_RETRIES,
    soft_time_limit=1500,
    time_limit=1800,
)
def run_shadow_sync(self, run_id: str) -> dict:
    result = ShadowSyncOrchestrator(SessionLocal).execute(UUID(run_id))
    if result.retryable and self.request.retries < MAX_DELIVERY_RETRIES:
        raise self.retry(countdown=backoff_seconds(self.request.retries))
    return {"run_id": run_id, "status": result.status, "reason": result.reason}


@celery_app.task(name="ledger.reap_abandoned_runs")
def reap_abandoned_runs() -> dict:
    """Run on demand; deliberately not in the Beat schedule."""
    try:
        ShadowPolicy.from_settings().require()
    except ShadowActivationRefused as refused:
        return {"status": "disabled", "reason": refused.code}
    with SessionLocal() as session, session.begin():
        actions = reap(session)
    for action in actions:  # after the commit, so a requeued task always sees the recorded state
        if action.action == "requeue":
            run_shadow_sync.delay(str(action.run_id))
    return {"status": "ok", "actions": [a.action for a in actions]}
