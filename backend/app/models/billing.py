"""Billing and subscription models for Heliox-AI."""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class SubscriptionStatus(str, Enum):
    """Stripe subscription status."""
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"


class BillingPlan(str, Enum):
    """Available billing plans."""
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


class TeamSubscription(Base, UUIDMixin, TimestampMixin):
    """
    Team subscription model for Stripe billing.
    
    Stores subscription status and Stripe IDs for billing management.
    """
    
    __tablename__ = "team_subscriptions"
    
    # Team reference (one-to-one)
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        comment="Reference to the team"
    )
    
    # Stripe IDs
    stripe_customer_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Stripe customer ID"
    )
    
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True,
        comment="Stripe subscription ID (null for free plan)"
    )
    
    # Subscription details
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(50),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
        index=True,
        comment="Subscription status"
    )
    
    plan: Mapped[BillingPlan] = mapped_column(
        String(50),
        nullable=False,
        default=BillingPlan.FREE,
        index=True,
        comment="Current billing plan"
    )
    
    # Billing period
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Current billing period start"
    )
    
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        index=True,
        comment="Current billing period end"
    )
    
    # Cancellation
    cancel_at_period_end: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether subscription cancels at period end"
    )
    
    canceled_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="When subscription was canceled"
    )
    
    # Trial
    trial_start: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Trial start date"
    )
    
    trial_end: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="Trial end date"
    )
    
    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="subscription")
    
    __table_args__ = (
        Index("ix_team_subscriptions_stripe_customer", "stripe_customer_id"),
        Index("ix_team_subscriptions_stripe_subscription", "stripe_subscription_id"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<TeamSubscription(team_id={self.team_id}, plan={self.plan.value}, "
            f"status={self.status.value})>"
        )


class TeamEntitlement(Base, UUIDMixin, TimestampMixin):
    """
    Team entitlement model for plan-based feature access.
    
    Defines limits and features available to a team based on their plan.
    """
    
    __tablename__ = "team_entitlements"
    
    # Team reference (one-to-one)
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        comment="Reference to the team"
    )
    
    # Plan
    plan: Mapped[BillingPlan] = mapped_column(
        String(50),
        nullable=False,
        default=BillingPlan.FREE,
        index=True,
        comment="Billing plan for these entitlements"
    )
    
    # Limits (JSONB for flexibility)
    limits: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default={},
        comment="Usage limits (max_teams, max_users, max_api_calls_per_day, etc.)"
    )
    
    # Features (JSONB for flexibility)
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default={},
        comment="Feature flags (integrations_enabled, forecasting_enabled, etc.)"
    )
    
    # Relationships
    team: Mapped["Team"] = relationship("Team", back_populates="entitlement")
    
    def __repr__(self) -> str:
        return f"<TeamEntitlement(team_id={self.team_id}, plan={self.plan.value})>"
