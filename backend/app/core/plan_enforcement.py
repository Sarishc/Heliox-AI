"""
Plan enforcement helpers for Heliox route handlers.

Three entry points:

  require_plan_for_team(db, team_id, *tiers)
    Call at the start of any route handler to gate access to a plan tier.
    Raises HTTP 403 with a structured body if the team is not on a qualifying plan.

  check_team_limit(db, team_id, limit_name, current_count)
    Call before creating a resource (API key, integration, etc.) to enforce
    per-plan quantity caps.  Raises HTTP 403 with a structured body if at limit.

  get_plan_features(db, team_id) -> PlanLimits
    Returns the full PlanLimits for the team's current plan — use in route
    handlers that need to return per-feature flags to the frontend.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.plans import (
    PlanLimits,
    PlanTier,
    billing_plan_to_tier,
    get_limits,
)
from app.models.billing import TeamSubscription

logger = logging.getLogger(__name__)

_UPGRADE_URL = "/billing/upgrade"


def _get_team_tier(db: Session, team_id: UUID) -> PlanTier:
    """
    Look up the team's current PlanTier from TeamSubscription.

    Falls back to STARTER when no subscription row exists (new teams, free users).
    """
    sub: Optional[TeamSubscription] = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub is None:
        return PlanTier.STARTER
    return billing_plan_to_tier(sub.plan)


def require_plan_for_team(db: Session, team_id: UUID, *tiers: PlanTier) -> None:
    """
    Assert that the team is on one of the specified plan tiers.

    Raises HTTP 403 with a structured JSON body if not:
      {
        "error": "plan_required",
        "message": "This feature requires the Growth plan or higher.",
        "required_plan": "growth",
        "current_plan": "starter",
        "upgrade_url": "/billing/upgrade"
      }
    """
    current_tier = _get_team_tier(db, team_id)
    if current_tier not in tiers:
        required = min(tiers, key=lambda t: list(PlanTier).index(t))
        logger.info(
            "Plan gate blocked team %s (plan=%s) from feature requiring %s",
            team_id,
            current_tier.value,
            [t.value for t in tiers],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "plan_required",
                "message": (f"This feature requires the {required.value.capitalize()} plan or higher."),
                "required_plan": required.value,
                "current_plan": current_tier.value,
                "upgrade_url": _UPGRADE_URL,
            },
        )


def check_team_limit(
    db: Session,
    team_id: UUID,
    limit_name: str,
    current_count: int,
) -> None:
    """
    Assert that the team has not reached a per-plan quantity limit.

    ``limit_name`` must be a field name on PlanLimits (e.g. "max_api_keys",
    "max_clusters").  Raises HTTP 403 with a structured JSON body if at limit:
      {
        "error": "limit_reached",
        "message": "You've reached the 5 api_keys limit on the Growth plan.",
        "limit": 5,
        "current": 5,
        "upgrade_url": "/billing/upgrade"
      }
    """
    tier = _get_team_tier(db, team_id)
    limits = get_limits(tier)
    max_val: int = getattr(limits, limit_name, 0)

    if max_val == -1:
        return  # unlimited

    if current_count >= max_val:
        logger.info(
            "Limit gate blocked team %s (plan=%s): %s at %d/%d",
            team_id,
            tier.value,
            limit_name,
            current_count,
            max_val,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "limit_reached",
                "message": (
                    f"You've reached the {max_val} {limit_name.replace('max_', '')} "
                    f"limit on the {tier.value.capitalize()} plan."
                ),
                "limit": max_val,
                "current": current_count,
                "upgrade_url": _UPGRADE_URL,
            },
        )


def get_plan_features(db: Session, team_id: UUID) -> PlanLimits:
    """Return the full PlanLimits for the team's current plan."""
    tier = _get_team_tier(db, team_id)
    return get_limits(tier)
