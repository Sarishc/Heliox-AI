"""API routes for Stripe billing and subscription management."""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.rbac import require_team_admin_or_api_key
from app.auth.team_resolution import TeamContext, verify_team_api_key_or_session
from app.core.config import get_settings
from app.core.db import get_db
from app.models.team_api_key import TeamAPIKey
from app.models.billing import TeamSubscription, TeamEntitlement, BillingPlan
from app.billing.stripe_client import (
    create_stripe_customer,
    create_checkout_session,
    create_customer_portal_session,
    sync_subscription_from_stripe,
    handle_subscription_deleted,
    update_team_entitlements,
)
from app.billing.plans import get_plan_info
from app.core.plan_enforcement import get_plan_features
from app.core.plans import billing_plan_to_tier
from app.integrations.models import IntegrationConnection
from app.models.team_member import TeamMember

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


def _require_stripe() -> None:
    """
    Raise HTTP 503 if Stripe is not configured.

    Call this at the start of any endpoint that creates Stripe sessions or
    performs Stripe API calls, so the user gets a clear error instead of an
    unhandled stripe.error.AuthenticationError.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("Billing is not configured on this instance. " "Contact your administrator to set up Stripe."),
        )


# Pydantic schemas
class CreateCheckoutSessionRequest(BaseModel):
    """Request to create checkout session."""

    plan: str = Field(description="Plan to subscribe to (starter, growth, enterprise)")
    success_url: str = Field(description="URL to redirect on success")
    cancel_url: str = Field(description="URL to redirect on cancel")


class CreateCheckoutSessionResponse(BaseModel):
    """Response with checkout session URL."""

    checkout_url: str = Field(description="Stripe Checkout URL")


class CreatePortalSessionRequest(BaseModel):
    """Request to create customer portal session."""

    return_url: str = Field(description="URL to return to after portal")


class CreatePortalSessionResponse(BaseModel):
    """Response with portal session URL."""

    portal_url: str = Field(description="Stripe Customer Portal URL")


class SubscriptionResponse(BaseModel):
    """Subscription status response."""

    team_id: str
    plan: str
    status: str
    stripe_customer_id: str
    stripe_subscription_id: Optional[str]
    current_period_end: Optional[str]
    cancel_at_period_end: bool
    limits: dict
    features: dict


class PricingPlan(BaseModel):
    """Pricing plan details."""

    plan: str
    name: str
    price: Any
    description: str
    limits: dict
    features: dict


@router.post("/create-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_checkout_session_endpoint(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    request_data: CreateCheckoutSessionRequest,
):
    """
    Create a Stripe Checkout session for subscription upgrade.

    Flow:
    1. Validate plan
    2. Get or create Stripe customer
    3. Create checkout session
    4. Return checkout URL
    """
    _require_stripe()

    # Validate plan
    try:
        plan = BillingPlan(request_data.plan)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan: {request_data.plan}",
        )

    # Free plan doesn't need checkout
    if plan == BillingPlan.FREE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create checkout session for free plan",
        )

    # Get or create subscription record
    subscription = db.query(TeamSubscription).filter(TeamSubscription.team_id == auth_ctx.team_id).first()

    if not subscription:
        # Create Stripe customer
        from app.models.team import Team

        team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()

        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

        stripe_customer_id = create_stripe_customer(team_id=auth_ctx.team_id, team_name=team.name)

        # Create subscription record
        subscription = TeamSubscription(
            team_id=auth_ctx.team_id,
            stripe_customer_id=stripe_customer_id,
            plan=BillingPlan.FREE,
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

    # Create checkout session
    try:
        checkout_url = create_checkout_session(
            team_id=auth_ctx.team_id,
            plan=plan,
            stripe_customer_id=subscription.stripe_customer_id,
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url,
        )

        return CreateCheckoutSessionResponse(checkout_url=checkout_url)

    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}",
        )


@router.post("/create-portal-session", response_model=CreatePortalSessionResponse)
async def create_portal_session_endpoint(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    request_data: CreatePortalSessionRequest,
):
    """
    Create a Stripe Customer Portal session for subscription management.

    Portal allows customers to:
    - Update payment method
    - View invoices
    - Cancel subscription
    - Update billing details
    """
    _require_stripe()

    # Get subscription record
    subscription = db.query(TeamSubscription).filter(TeamSubscription.team_id == auth_ctx.team_id).first()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this team",
        )

    # Create portal session
    try:
        portal_url = create_customer_portal_session(
            stripe_customer_id=subscription.stripe_customer_id,
            return_url=request_data.return_url,
        )

        return CreatePortalSessionResponse(portal_url=portal_url)

    except Exception as e:
        logger.error(f"Failed to create portal session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}",
        )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
):
    """
    Get current subscription status and entitlements.

    Returns subscription details and plan limits/features.
    Supports both API key and session (cookie) auth.
    """
    # Get subscription
    subscription = db.query(TeamSubscription).filter(TeamSubscription.team_id == auth_ctx.team_id).first()

    # Get entitlements
    entitlement = db.query(TeamEntitlement).filter(TeamEntitlement.team_id == auth_ctx.team_id).first()

    # If no subscription exists, create free tier — requires Stripe to be configured
    if not subscription:
        _require_stripe()

        from app.models.team import Team

        team = db.query(Team).filter(Team.id == auth_ctx.team_id).first()

        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

        # Create Stripe customer
        stripe_customer_id = create_stripe_customer(team_id=auth_ctx.team_id, team_name=team.name)

        # Create subscription record
        subscription = TeamSubscription(
            team_id=auth_ctx.team_id,
            stripe_customer_id=stripe_customer_id,
            plan=BillingPlan.FREE,
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        # Create entitlements
        entitlement = update_team_entitlements(db, auth_ctx.team_id, BillingPlan.FREE)

    # If no entitlement exists, create it
    if not entitlement:
        entitlement = update_team_entitlements(db, auth_ctx.team_id, subscription.plan)

    return SubscriptionResponse(
        team_id=str(subscription.team_id),
        plan=subscription.plan.value,
        status=subscription.status.value,
        stripe_customer_id=subscription.stripe_customer_id,
        stripe_subscription_id=subscription.stripe_subscription_id,
        current_period_end=(subscription.current_period_end.isoformat() if subscription.current_period_end else None),
        cancel_at_period_end=subscription.cancel_at_period_end,
        limits=entitlement.limits,
        features=entitlement.features,
    )


@router.get("/plans", response_model=list[PricingPlan])
async def get_pricing_plans():
    """
    Get available pricing plans with details.

    Returns all plans with limits and features for display in pricing page.
    """
    plans = []

    for plan_enum in BillingPlan:
        plan_info = get_plan_info(plan_enum)
        plans.append(
            PricingPlan(
                plan=plan_enum.value,
                name=plan_info["name"],
                price=plan_info["price"],
                description=plan_info["description"],
                limits=plan_info["limits"],
                features=plan_info["features"],
            )
        )

    return plans


@router.get("/plan", summary="Get current plan limits and usage")
async def get_plan_details(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(verify_team_api_key_or_session),
):
    """
    Return the team's current plan, its limits, live usage counters,
    and a Stripe portal URL for managing the subscription.

    Response shape:
      {
        "plan": "growth",
        "limits": { "max_clusters": 5, "history_days": 365, ... },
        "usage": { "clusters": 2, "api_keys": 1, "team_members": 4 },
        "stripe_portal_url": "https://billing.stripe.com/..."
      }
    """
    team_id = auth_ctx.team_id

    limits = get_plan_features(db, team_id)

    # Live usage counters
    cluster_count = (
        db.query(IntegrationConnection)
        .filter(
            IntegrationConnection.team_id == team_id,
            IntegrationConnection.status != "deleted",
        )
        .count()
    )
    api_key_count = db.query(TeamAPIKey).filter(TeamAPIKey.team_id == team_id, TeamAPIKey.is_active == True).count()
    member_count = db.query(TeamMember).filter(TeamMember.team_id == team_id).count()

    # Stripe portal URL (best-effort — empty string if not configured or no subscription)
    portal_url = ""
    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub and sub.stripe_customer_id and settings.STRIPE_SECRET_KEY:
        try:
            from app.billing.stripe_client import create_customer_portal_session

            portal_url = create_customer_portal_session(
                stripe_customer_id=sub.stripe_customer_id,
                return_url="/billing",
            )
        except Exception:
            pass

    plan_tier = billing_plan_to_tier(sub.plan) if sub else "starter"
    plan_value = plan_tier.value if hasattr(plan_tier, "value") else str(plan_tier)

    return {
        "plan": plan_value,
        "limits": {
            "max_clusters": limits.max_clusters,
            "history_days": limits.history_days,
            "max_api_keys": limits.max_api_keys,
            "max_team_members": limits.max_team_members,
            "slack_alerts": limits.slack_alerts,
            "sso_enabled": limits.sso_enabled,
            "api_access": limits.api_access,
            "custom_rbac": limits.custom_rbac,
            "dedicated_csm": limits.dedicated_csm,
        },
        "usage": {
            "clusters": cluster_count,
            "api_keys": api_key_count,
            "team_members": member_count,
        },
        "stripe_portal_url": portal_url,
    }


@router.post(
    "/upgrade",
    response_model=CreateCheckoutSessionResponse,
    summary="Start Stripe Checkout to upgrade to Growth",
)
async def upgrade_to_growth(
    *,
    db: Session = Depends(get_db),
    auth_ctx: Union[TeamAPIKey, TeamContext] = Depends(require_team_admin_or_api_key),
    success_url: str = "/billing?upgraded=true",
    cancel_url: str = "/billing",
):
    """
    Create a Stripe Checkout session for upgrading to the Growth plan.

    Shorthand for POST /billing/create-checkout-session with plan=growth and
    sensible default redirect URLs. Returns { "checkout_url": "..." }.
    """
    _require_stripe()

    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == auth_ctx.team_id).first()

    if not sub:
        from app.models.team import Team as TeamModel

        team = db.query(TeamModel).filter(TeamModel.id == auth_ctx.team_id).first()
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
        stripe_customer_id = create_stripe_customer(
            team_id=auth_ctx.team_id,
            team_name=team.name,
        )
        sub = TeamSubscription(
            team_id=auth_ctx.team_id,
            stripe_customer_id=stripe_customer_id,
            plan=BillingPlan.FREE,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)

    try:
        checkout_url = create_checkout_session(
            team_id=auth_ctx.team_id,
            plan=BillingPlan.GROWTH,
            stripe_customer_id=sub.stripe_customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return CreateCheckoutSessionResponse(checkout_url=checkout_url)
    except Exception as e:
        logger.error("Failed to create upgrade checkout session: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start upgrade: {str(e)}",
        )


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhooks.

    Processes events:
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - checkout.session.completed

    Verifies webhook signature for security.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    # Handle event
    event_type = event["type"]
    logger.info(f"Received Stripe webhook: {event_type}")

    try:
        if event_type == "customer.subscription.created":
            subscription = event["data"]["object"]
            sync_subscription_from_stripe(db, subscription)

        elif event_type == "customer.subscription.updated":
            subscription = event["data"]["object"]
            sync_subscription_from_stripe(db, subscription)

        elif event_type == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            handle_subscription_deleted(db, subscription)

        elif event_type == "checkout.session.completed":
            session = event["data"]["object"]
            # subscription.created/updated events handle the plan sync;
            # log here for audit trail only
            logger.info(
                f"Checkout completed: session={session['id']} "
                f"customer={session.get('customer')} "
                f"subscription={session.get('subscription')}"
            )

        elif event_type == "invoice.paid":
            # Payment succeeded — ensure subscription is active in DB
            invoice = event["data"]["object"]
            subscription_id = invoice.get("subscription")
            if subscription_id:
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription_id)
                    sync_subscription_from_stripe(db, stripe_sub)
                    logger.info(f"invoice.paid: synced subscription {subscription_id} " f"(invoice {invoice['id']})")
                except stripe.error.StripeError as e:
                    logger.error(f"Failed to retrieve subscription {subscription_id}: {e}")
            else:
                logger.info(f"invoice.paid for one-time invoice {invoice['id']} — no subscription to sync")

        elif event_type == "invoice.payment_failed":
            # Payment failed — mark subscription past_due and log for support
            invoice = event["data"]["object"]
            subscription_id = invoice.get("subscription")
            customer_id = invoice.get("customer")
            attempt_count = invoice.get("attempt_count", 0)
            next_payment_attempt = invoice.get("next_payment_attempt")

            logger.warning(
                f"invoice.payment_failed: customer={customer_id} "
                f"subscription={subscription_id} attempt={attempt_count} "
                f"next_attempt={next_payment_attempt} invoice={invoice['id']}"
            )

            if subscription_id:
                # Mark subscription as past_due in our DB immediately
                team_sub = (
                    db.query(TeamSubscription)
                    .filter(TeamSubscription.stripe_subscription_id == subscription_id)
                    .first()
                )
                if team_sub:
                    team_sub.status = "past_due"
                    db.add(team_sub)
                    db.commit()
                    logger.info(f"Marked subscription {subscription_id} as past_due " f"(team {team_sub.team_id})")
                else:
                    logger.warning(f"invoice.payment_failed: no local subscription found for {subscription_id}")

        else:
            logger.info(f"Unhandled webhook event type: {event_type}")

    except Exception as e:
        # Log and return 200 so Stripe does NOT retry — retries for transient errors
        # are handled by re-querying Stripe on the next subscription sync.
        logger.error(f"Error processing webhook {event_type}: {e}", exc_info=True)
        # Return 200 to prevent Stripe infinite retry loop on our processing bugs
        return {"status": "error", "detail": str(e)}

    return {"status": "success"}
