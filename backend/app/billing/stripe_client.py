"""Stripe API client and utilities."""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import stripe
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing import (
    TeamSubscription,
    TeamEntitlement,
    BillingPlan,
    SubscriptionStatus,
)
from app.billing.plans import get_plan_entitlements

logger = logging.getLogger(__name__)
settings = get_settings()


def _stripe_metadata(resource: Any) -> dict[str, str]:
    """Return Stripe metadata as a normal dict across SDK/API versions."""
    raw = resource.get("metadata") if isinstance(resource, dict) else getattr(resource, "metadata", None)
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "to_dict"):
        return raw.to_dict()
    return dict(raw)


def _subscription_period(subscription: Any) -> tuple[int, int]:
    """Read billing period from either legacy top-level or current item fields."""
    start = getattr(subscription, "current_period_start", None)
    end = getattr(subscription, "current_period_end", None)
    if start is not None and end is not None:
        return start, end

    items = getattr(subscription, "items", None)
    item_data = getattr(items, "data", None) if items is not None else None
    if not item_data:
        raise ValueError("Subscription missing current billing period")
    return item_data[0].current_period_start, item_data[0].current_period_end


# Initialize Stripe
if hasattr(settings, "STRIPE_SECRET_KEY") and settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY not configured - Stripe features disabled")


def create_stripe_customer(team_id: UUID, team_name: str, email: Optional[str] = None) -> str:
    """
    Create a Stripe customer.

    Args:
        team_id: Team UUID
        team_name: Team name
        email: Optional email address

    Returns:
        Stripe customer ID
    """
    customer = stripe.Customer.create(
        metadata={"team_id": str(team_id)},
        name=team_name,
        email=email,
        description=f"Heliox Team: {team_name}",
    )

    logger.info(f"Created Stripe customer {customer.id} for team {team_id}")
    return customer.id


def create_checkout_session(
    team_id: UUID,
    plan: BillingPlan,
    stripe_customer_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """
    Create a Stripe Checkout session for subscription.

    Args:
        team_id: Team UUID
        plan: Billing plan to subscribe to
        stripe_customer_id: Stripe customer ID
        success_url: URL to redirect on success
        cancel_url: URL to redirect on cancel

    Returns:
        Checkout session URL
    """
    # Get price ID for plan from settings
    price_id = get_price_id_for_plan(plan)

    if not price_id:
        raise ValueError(f"No price ID configured for plan {plan.value}")

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        line_items=[
            {
                "price": price_id,
                "quantity": 1,
            }
        ],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"team_id": str(team_id), "plan": plan.value},
        subscription_data={
            "metadata": {"team_id": str(team_id), "plan": plan.value},
        },
        allow_promotion_codes=True,
        billing_address_collection="required",
    )

    logger.info(f"Created checkout session {session.id} for team {team_id}, plan {plan.value}")
    return session.url


def create_customer_portal_session(stripe_customer_id: str, return_url: str) -> str:
    """
    Create a Stripe Customer Portal session.

    Args:
        stripe_customer_id: Stripe customer ID
        return_url: URL to return to after portal

    Returns:
        Customer portal URL
    """
    session = stripe.billing_portal.Session.create(customer=stripe_customer_id, return_url=return_url)

    logger.info(f"Created customer portal session for customer {stripe_customer_id}")
    return session.url


def get_price_id_for_plan(plan: BillingPlan) -> Optional[str]:
    """
    Get Stripe price ID for a billing plan.

    Args:
        plan: Billing plan

    Returns:
        Stripe price ID or None
    """
    price_map = {
        BillingPlan.STARTER: getattr(settings, "STRIPE_PRICE_ID_STARTER", None),
        BillingPlan.GROWTH: getattr(settings, "STRIPE_PRICE_ID_GROWTH", None),
        BillingPlan.ENTERPRISE: getattr(settings, "STRIPE_PRICE_ID_ENTERPRISE", None),
    }

    return price_map.get(plan)


def sync_subscription_from_stripe(db: Session, stripe_subscription: stripe.Subscription) -> TeamSubscription:
    """
    Sync subscription from Stripe to database.

    Args:
        db: Database session
        stripe_subscription: Stripe subscription object

    Returns:
        Updated TeamSubscription
    """
    # Extract team_id from metadata
    metadata = _stripe_metadata(stripe_subscription)
    team_id_str = metadata.get("team_id")
    if not team_id_str:
        raise ValueError("Subscription missing team_id in metadata")

    team_id = UUID(team_id_str)

    # Determine plan from subscription
    plan = determine_plan_from_subscription(stripe_subscription)

    # Get or create subscription record
    subscription = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()

    if not subscription:
        subscription = TeamSubscription(
            team_id=team_id,
            stripe_customer_id=stripe_subscription.customer,
            stripe_subscription_id=stripe_subscription.id,
        )
        db.add(subscription)

    # Update subscription details
    subscription.stripe_subscription_id = stripe_subscription.id
    subscription.status = SubscriptionStatus(stripe_subscription.status)
    subscription.plan = plan
    period_start, period_end = _subscription_period(stripe_subscription)
    subscription.current_period_start = datetime.fromtimestamp(period_start)
    subscription.current_period_end = datetime.fromtimestamp(period_end)
    # Current Stripe API versions may represent portal-scheduled cancellation
    # with an explicit `cancel_at` timestamp while `cancel_at_period_end` is
    # false. Preserve the product-level meaning for the local schema/UI.
    subscription.cancel_at_period_end = bool(
        stripe_subscription.cancel_at_period_end or getattr(stripe_subscription, "cancel_at", None)
    )

    if stripe_subscription.canceled_at:
        subscription.canceled_at = datetime.fromtimestamp(stripe_subscription.canceled_at)

    if stripe_subscription.trial_start:
        subscription.trial_start = datetime.fromtimestamp(stripe_subscription.trial_start)

    if stripe_subscription.trial_end:
        subscription.trial_end = datetime.fromtimestamp(stripe_subscription.trial_end)

    db.commit()
    db.refresh(subscription)

    # Update entitlements
    update_team_entitlements(db, team_id, plan)

    logger.info(f"Synced subscription {subscription.id} for team {team_id}, plan {plan.value}")

    return subscription


def determine_plan_from_subscription(
    stripe_subscription: stripe.Subscription,
) -> BillingPlan:
    """
    Determine billing plan from Stripe subscription.

    Args:
        stripe_subscription: Stripe subscription object

    Returns:
        BillingPlan enum
    """
    # Check metadata first
    metadata = _stripe_metadata(stripe_subscription)
    if "plan" in metadata:
        plan_str = metadata["plan"]
        try:
            return BillingPlan(plan_str)
        except ValueError:
            pass

    # Check price IDs
    if stripe_subscription.items and len(stripe_subscription.items.data) > 0:
        price_id = stripe_subscription.items.data[0].price.id

        if price_id == getattr(settings, "STRIPE_PRICE_ID_STARTER", None):
            return BillingPlan.STARTER
        elif price_id == getattr(settings, "STRIPE_PRICE_ID_GROWTH", None):
            return BillingPlan.GROWTH
        elif price_id == getattr(settings, "STRIPE_PRICE_ID_ENTERPRISE", None):
            return BillingPlan.ENTERPRISE

    # Default to free if can't determine
    return BillingPlan.FREE


def update_team_entitlements(db: Session, team_id: UUID, plan: BillingPlan) -> TeamEntitlement:
    """
    Update team entitlements based on plan.

    Args:
        db: Database session
        team_id: Team UUID
        plan: Billing plan

    Returns:
        Updated TeamEntitlement
    """
    # Get entitlements for plan
    entitlements = get_plan_entitlements(plan)

    # Get or create entitlement record
    entitlement = db.query(TeamEntitlement).filter(TeamEntitlement.team_id == team_id).first()

    if not entitlement:
        entitlement = TeamEntitlement(team_id=team_id)
        db.add(entitlement)

    # Update entitlements
    entitlement.plan = plan
    entitlement.limits = entitlements["limits"]
    entitlement.features = entitlements["features"]

    db.commit()
    db.refresh(entitlement)

    logger.info(f"Updated entitlements for team {team_id} to plan {plan.value}")

    return entitlement


def handle_subscription_deleted(db: Session, stripe_subscription: stripe.Subscription):
    """
    Handle subscription deletion (downgrade to free).

    Args:
        db: Database session
        stripe_subscription: Stripe subscription object
    """
    team_id_str = _stripe_metadata(stripe_subscription).get("team_id")
    if not team_id_str:
        logger.warning(f"Subscription {stripe_subscription.id} missing team_id in metadata")
        return

    team_id = UUID(team_id_str)

    # Update subscription to canceled
    subscription = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()

    if subscription:
        subscription.status = SubscriptionStatus.CANCELED
        subscription.plan = BillingPlan.FREE
        subscription.stripe_subscription_id = None
        subscription.canceled_at = datetime.utcnow()
        db.commit()

    # Downgrade entitlements to free plan
    update_team_entitlements(db, team_id, BillingPlan.FREE)

    logger.info(f"Downgraded team {team_id} to free plan after subscription deletion")
