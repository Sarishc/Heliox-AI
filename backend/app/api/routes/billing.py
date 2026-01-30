"""API routes for Stripe billing and subscription management."""
import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import verify_team_api_key
from app.models.team_api_key import TeamAPIKey
from app.models.billing import TeamSubscription, TeamEntitlement, BillingPlan
from app.billing.stripe_client import (
    create_stripe_customer,
    create_checkout_session,
    create_customer_portal_session,
    sync_subscription_from_stripe,
    handle_subscription_deleted,
    update_team_entitlements
)
from app.billing.plans import PLAN_DEFINITIONS, get_plan_info

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


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
    price: any
    description: str
    limits: dict
    features: dict


@router.post("/create-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_checkout_session_endpoint(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    request_data: CreateCheckoutSessionRequest
):
    """
    Create a Stripe Checkout session for subscription upgrade.
    
    Flow:
    1. Validate plan
    2. Get or create Stripe customer
    3. Create checkout session
    4. Return checkout URL
    """
    # Validate plan
    try:
        plan = BillingPlan(request_data.plan)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan: {request_data.plan}"
        )
    
    # Free plan doesn't need checkout
    if plan == BillingPlan.FREE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create checkout session for free plan"
        )
    
    # Get or create subscription record
    subscription = db.query(TeamSubscription).filter(
        TeamSubscription.team_id == api_key.team_id
    ).first()
    
    if not subscription:
        # Create Stripe customer
        from app.models.team import Team
        team = db.query(Team).filter(Team.id == api_key.team_id).first()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        stripe_customer_id = create_stripe_customer(
            team_id=api_key.team_id,
            team_name=team.name
        )
        
        # Create subscription record
        subscription = TeamSubscription(
            team_id=api_key.team_id,
            stripe_customer_id=stripe_customer_id,
            plan=BillingPlan.FREE
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
    
    # Create checkout session
    try:
        checkout_url = create_checkout_session(
            team_id=api_key.team_id,
            plan=plan,
            stripe_customer_id=subscription.stripe_customer_id,
            success_url=request_data.success_url,
            cancel_url=request_data.cancel_url
        )
        
        return CreateCheckoutSessionResponse(checkout_url=checkout_url)
    
    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}"
        )


@router.post("/create-portal-session", response_model=CreatePortalSessionResponse)
async def create_portal_session_endpoint(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key),
    request_data: CreatePortalSessionRequest
):
    """
    Create a Stripe Customer Portal session for subscription management.
    
    Portal allows customers to:
    - Update payment method
    - View invoices
    - Cancel subscription
    - Update billing details
    """
    # Get subscription record
    subscription = db.query(TeamSubscription).filter(
        TeamSubscription.team_id == api_key.team_id
    ).first()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this team"
        )
    
    # Create portal session
    try:
        portal_url = create_customer_portal_session(
            stripe_customer_id=subscription.stripe_customer_id,
            return_url=request_data.return_url
        )
        
        return CreatePortalSessionResponse(portal_url=portal_url)
    
    except Exception as e:
        logger.error(f"Failed to create portal session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}"
        )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    *,
    db: Session = Depends(get_db),
    api_key: TeamAPIKey = Depends(verify_team_api_key)
):
    """
    Get current subscription status and entitlements.
    
    Returns subscription details and plan limits/features.
    """
    # Get subscription
    subscription = db.query(TeamSubscription).filter(
        TeamSubscription.team_id == api_key.team_id
    ).first()
    
    # Get entitlements
    entitlement = db.query(TeamEntitlement).filter(
        TeamEntitlement.team_id == api_key.team_id
    ).first()
    
    # If no subscription exists, create free tier
    if not subscription:
        from app.models.team import Team
        team = db.query(Team).filter(Team.id == api_key.team_id).first()
        
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found"
            )
        
        # Create Stripe customer
        stripe_customer_id = create_stripe_customer(
            team_id=api_key.team_id,
            team_name=team.name
        )
        
        # Create subscription record
        subscription = TeamSubscription(
            team_id=api_key.team_id,
            stripe_customer_id=stripe_customer_id,
            plan=BillingPlan.FREE
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)
        
        # Create entitlements
        entitlement = update_team_entitlements(db, api_key.team_id, BillingPlan.FREE)
    
    # If no entitlement exists, create it
    if not entitlement:
        entitlement = update_team_entitlements(db, api_key.team_id, subscription.plan)
    
    return SubscriptionResponse(
        team_id=str(subscription.team_id),
        plan=subscription.plan.value,
        status=subscription.status.value,
        stripe_customer_id=subscription.stripe_customer_id,
        stripe_subscription_id=subscription.stripe_subscription_id,
        current_period_end=subscription.current_period_end.isoformat() if subscription.current_period_end else None,
        cancel_at_period_end=subscription.cancel_at_period_end,
        limits=entitlement.limits,
        features=entitlement.features
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
        plans.append(PricingPlan(
            plan=plan_enum.value,
            name=plan_info["name"],
            price=plan_info["price"],
            description=plan_info["description"],
            limits=plan_info["limits"],
            features=plan_info["features"]
        ))
    
    return plans


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
            detail="Missing stripe-signature header"
        )
    
    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )
    
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
            # Subscription is created/updated via subscription.created/updated events
            logger.info(f"Checkout session completed: {session['id']}")
        
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
    
    except Exception as e:
        logger.error(f"Error processing webhook {event_type}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing webhook: {str(e)}"
        )
    
    return {"status": "success"}
