"""
Stripe metering export service.

Exports usage rollups to Stripe Billing Meter Events for usage-based billing.
Idempotent, retry-safe, and auditable.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID

import stripe
from stripe import StripeError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing import BillingPlan, TeamSubscription
from app.models.stripe_meter_export import StripeMeterExport
from app.models.usage import UsageDailyRollup, UsageEventType

logger = logging.getLogger(__name__)

# Map internal event types to config keys
EVENT_TYPE_TO_CONFIG = {
    UsageEventType.API_REQUEST: "STRIPE_METER_API_REQUESTS",
    UsageEventType.INGESTION: "STRIPE_METER_INGESTION",
    UsageEventType.GPU_NODE: "STRIPE_METER_GPU_NODES",
    UsageEventType.SEAT: "STRIPE_METER_SEATS",
}

PAID_PLANS = {BillingPlan.STARTER, BillingPlan.GROWTH, BillingPlan.ENTERPRISE}
ACTIVE_STATUSES = {"active", "trialing"}


def _get_meter_event_name(event_type: UsageEventType) -> Optional[str]:
    """Get Stripe meter event name from config. Empty string = skip."""
    settings = get_settings()
    key = EVENT_TYPE_TO_CONFIG.get(event_type)
    if not key:
        return None
    name = getattr(settings, key, None) or ""
    return name.strip() or None


def _make_identifier(team_id: UUID, export_date: date, event_type: str) -> str:
    """Create idempotency identifier for Stripe (max 100 chars)."""
    return f"heliox_{team_id}_{export_date}_{event_type}"[:100]


def _teams_eligible_for_metering(db: Session) -> set[UUID]:
    """Teams with active paid subscription and stripe_customer_id."""
    rows = (
        db.query(TeamSubscription.team_id)
        .filter(
            TeamSubscription.stripe_customer_id.isnot(None),
            TeamSubscription.stripe_customer_id != "",
            TeamSubscription.status.in_(ACTIVE_STATUSES),
            TeamSubscription.plan.in_([p.value for p in PAID_PLANS]),
        )
        .all()
    )
    return {UUID(str(r.team_id)) for r in rows}


def export_usage_to_stripe(
    db: Session,
    export_date: date,
    *,
    dry_run: bool = False,
) -> dict:
    """
    Export usage rollups for a date to Stripe meter events.

    Idempotent: skips (team, date, event_type) already exported successfully.
    Retry-safe: failed exports can be retried.

    Args:
        db: Database session
        export_date: Date of rollups to export
        dry_run: If True, do not call Stripe or persist exports

    Returns:
        {exported: int, skipped: int, failed: int, errors: list}
    """
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        logger.info("Stripe metering skipped: STRIPE_SECRET_KEY not configured")
        return {
            "exported": 0,
            "skipped": 0,
            "failed": 0,
            "errors": ["Stripe not configured"],
        }

    eligible = _teams_eligible_for_metering(db)
    if not eligible:
        logger.info("No teams eligible for Stripe metering")
        return {"exported": 0, "skipped": 0, "failed": 0, "errors": []}

    rollups = (
        db.query(UsageDailyRollup)
        .filter(
            UsageDailyRollup.team_id.in_(eligible),
            UsageDailyRollup.date == export_date,
            UsageDailyRollup.total_quantity > 0,
        )
        .all()
    )

    exported = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    # Get stripe_customer_id per team
    sub_map = {
        UUID(str(s.team_id)): s.stripe_customer_id
        for s in db.query(TeamSubscription).filter(TeamSubscription.team_id.in_(eligible)).all()
    }

    for rollup in rollups:
        team_id = UUID(str(rollup.team_id))
        event_type = rollup.event_type.value if isinstance(rollup.event_type, UsageEventType) else rollup.event_type
        meter_name = _get_meter_event_name(
            UsageEventType(event_type) if isinstance(event_type, str) else rollup.event_type
        )
        if not meter_name:
            skipped += 1
            continue

        # Check if already succeeded
        existing = (
            db.query(StripeMeterExport)
            .filter(
                StripeMeterExport.team_id == team_id,
                StripeMeterExport.export_date == export_date,
                StripeMeterExport.event_type == event_type,
            )
            .first()
        )
        if existing and existing.status == "succeeded":
            skipped += 1
            continue

        stripe_customer_id = sub_map.get(team_id)
        if not stripe_customer_id:
            skipped += 1
            continue

        identifier = _make_identifier(team_id, export_date, event_type)
        quantity = int(rollup.total_quantity or 0)
        if quantity <= 0:
            skipped += 1
            continue

        if dry_run:
            logger.info(f"[dry_run] Would export {team_id} {export_date} {event_type} qty={quantity}")
            exported += 1
            continue

        try:
            stripe.billing.MeterEvent.create(
                event_name=meter_name,
                payload={
                    "stripe_customer_id": stripe_customer_id,
                    "value": quantity,
                },
                identifier=identifier,
                timestamp=int(datetime.combine(export_date, datetime.min.time()).timestamp()),
            )

            # Upsert export record
            if existing:
                existing.status = "succeeded"
                existing.quantity = quantity
                existing.error_message = None
                existing.updated_at = datetime.utcnow()
            else:
                db.add(
                    StripeMeterExport(
                        team_id=team_id,
                        export_date=export_date,
                        event_type=event_type,
                        quantity=quantity,
                        stripe_identifier=identifier,
                        status="succeeded",
                    )
                )
            db.commit()
            exported += 1
            logger.debug(f"Exported meter event: {meter_name} team={team_id} qty={quantity}")

        except StripeError as e:
            err_msg = str(e)
            errors.append(f"{team_id}:{event_type}: {err_msg}")
            failed += 1
            if existing:
                existing.status = "failed"
                existing.error_message = err_msg[:2000]  # limit length
                existing.updated_at = datetime.utcnow()
            else:
                db.add(
                    StripeMeterExport(
                        team_id=team_id,
                        export_date=export_date,
                        event_type=event_type,
                        quantity=quantity,
                        stripe_identifier=identifier,
                        status="failed",
                        error_message=err_msg[:2000],
                    )
                )
            db.commit()
            logger.warning(f"Stripe meter export failed: {e}")
        except Exception as e:
            err_msg = str(e)
            errors.append(f"{team_id}:{event_type}: {err_msg}")
            failed += 1
            db.rollback()
            logger.exception("Unexpected error during Stripe metering")

    return {
        "exported": exported,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:20],  # cap for response
    }
