"""Celery tasks for budget guardrails."""
from app.celery_app import celery_app
from app.core.db import SessionLocal
from app.models.budget import BudgetPolicy
from app.services.budget_guardrails import BudgetGuardrailsService


@celery_app.task(name="app.tasks.budget_tasks.budget_guardrails_tick")
def budget_guardrails_tick() -> None:
    db = SessionLocal()
    try:
        policies = db.query(BudgetPolicy).filter(BudgetPolicy.is_enabled.is_(True)).all()
        service = BudgetGuardrailsService(db)
        for policy in policies:
            service.evaluate_policy(policy, send_alerts=True)
    finally:
        db.close()
