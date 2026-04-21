"""
Plan tier definitions and limits for Heliox billing enforcement.

Three public-facing tiers:
  Starter  — free,     1 cluster, 30-day history, no API keys, no Slack, no SSO
  Growth   — $199/mo,  5 clusters, 365-day history, 5 API keys, Slack alerts
  Enterprise — custom, unlimited everything, SSO, custom RBAC, dedicated CSM

Mapping to the internal BillingPlan enum (stored in DB):
  PlanTier.STARTER   → BillingPlan.FREE  (and legacy BillingPlan.STARTER)
  PlanTier.GROWTH    → BillingPlan.GROWTH
  PlanTier.ENTERPRISE → BillingPlan.ENTERPRISE
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from app.models.billing import BillingPlan


class PlanTier(str, Enum):
    """Public-facing plan tiers used by the enforcement layer."""

    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class PlanLimits:
    max_clusters: int  # max cloud integrations; -1 = unlimited
    history_days: int  # cost data retention; -1 = unlimited
    max_api_keys: int  # team API keys; -1 = unlimited
    max_team_members: int  # users per team; -1 = unlimited
    slack_alerts: bool
    sso_enabled: bool
    api_access: bool
    custom_rbac: bool
    dedicated_csm: bool


PLAN_LIMITS: Dict[PlanTier, PlanLimits] = {
    PlanTier.STARTER: PlanLimits(
        max_clusters=1,
        history_days=30,
        max_api_keys=0,
        max_team_members=3,
        slack_alerts=False,
        sso_enabled=False,
        api_access=False,
        custom_rbac=False,
        dedicated_csm=False,
    ),
    PlanTier.GROWTH: PlanLimits(
        max_clusters=5,
        history_days=365,
        max_api_keys=5,
        max_team_members=25,
        slack_alerts=True,
        sso_enabled=False,
        api_access=True,
        custom_rbac=False,
        dedicated_csm=False,
    ),
    PlanTier.ENTERPRISE: PlanLimits(
        max_clusters=-1,
        history_days=-1,
        max_api_keys=-1,
        max_team_members=-1,
        slack_alerts=True,
        sso_enabled=True,
        api_access=True,
        custom_rbac=True,
        dedicated_csm=True,
    ),
}

# Map internal BillingPlan values → public PlanTier for enforcement checks.
# Both FREE and legacy STARTER ($49) resolve to PlanTier.STARTER.
BILLING_PLAN_TO_TIER: Dict[BillingPlan, PlanTier] = {
    BillingPlan.FREE: PlanTier.STARTER,
    BillingPlan.STARTER: PlanTier.STARTER,  # legacy $49 tier
    BillingPlan.GROWTH: PlanTier.GROWTH,
    BillingPlan.ENTERPRISE: PlanTier.ENTERPRISE,
}


def get_limits(plan: PlanTier) -> PlanLimits:
    """Return the PlanLimits for a given PlanTier."""
    return PLAN_LIMITS[plan]


def billing_plan_to_tier(plan: BillingPlan) -> PlanTier:
    """Convert an internal BillingPlan to its public PlanTier."""
    return BILLING_PLAN_TO_TIER.get(plan, PlanTier.STARTER)
