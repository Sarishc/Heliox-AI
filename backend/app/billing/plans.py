"""Billing plans and entitlements configuration."""

from typing import Dict, Any
from app.models.billing import BillingPlan

# Plan definitions with limits and features
PLAN_DEFINITIONS: Dict[BillingPlan, Dict[str, Any]] = {
    BillingPlan.FREE: {
        "name": "Starter",
        "price": 0,
        "description": "For individuals and small teams getting started",
        "limits": {
            "max_teams": 1,
            "max_users": 3,
            "max_api_calls_per_day": 1000,
            "max_integrations": 1,
            "max_api_keys": 0,
            "max_gpu_nodes": 5,
            "data_retention_days": 30,
        },
        "features": {
            "integrations_enabled": True,
            "forecasting_enabled": False,
            "alerts_enabled": False,
            "api_access": False,
            "custom_reports": False,
            "sso_enabled": False,
            "priority_support": False,
            "white_label": False,
            "custom_rbac": False,
            "dedicated_csm": False,
        },
    },
    BillingPlan.STARTER: {
        "name": "Starter (legacy)",
        "price": 49,
        "description": "Legacy $49 plan — grandfathered accounts",
        "limits": {
            "max_teams": 3,
            "max_users": 10,
            "max_api_calls_per_day": 10000,
            "max_integrations": 2,
            "max_api_keys": 2,
            "max_gpu_nodes": 20,
            "data_retention_days": 90,
        },
        "features": {
            "integrations_enabled": True,
            "forecasting_enabled": True,
            "alerts_enabled": True,
            "api_access": True,
            "custom_reports": False,
            "sso_enabled": False,
            "priority_support": False,
            "white_label": False,
            "custom_rbac": False,
            "dedicated_csm": False,
        },
    },
    BillingPlan.GROWTH: {
        "name": "Growth",
        "price": 199,
        "description": "For teams scaling their GPU operations",
        "limits": {
            "max_teams": 10,
            "max_users": 25,
            "max_api_calls_per_day": 100000,
            "max_integrations": 5,
            "max_api_keys": 5,
            "max_gpu_nodes": 100,
            "data_retention_days": 365,
        },
        "features": {
            "integrations_enabled": True,
            "forecasting_enabled": True,
            "alerts_enabled": True,
            "api_access": True,
            "custom_reports": True,
            "sso_enabled": False,
            "priority_support": True,
            "white_label": False,
            "custom_rbac": False,
            "dedicated_csm": False,
        },
    },
    BillingPlan.ENTERPRISE: {
        "name": "Enterprise",
        "price": "Custom",
        "description": "For large organizations with advanced needs",
        "limits": {
            "max_teams": -1,
            "max_users": -1,
            "max_api_calls_per_day": -1,
            "max_integrations": -1,
            "max_api_keys": -1,
            "max_gpu_nodes": -1,
            "data_retention_days": -1,
        },
        "features": {
            "integrations_enabled": True,
            "forecasting_enabled": True,
            "alerts_enabled": True,
            "api_access": True,
            "custom_reports": True,
            "sso_enabled": True,
            "priority_support": True,
            "white_label": True,
            "custom_rbac": True,
            "dedicated_csm": True,
        },
    },
}


def get_plan_entitlements(plan: BillingPlan) -> Dict[str, Any]:
    """
    Get entitlements for a specific plan.

    Args:
        plan: Billing plan

    Returns:
        Dictionary with limits and features
    """
    plan_def = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS[BillingPlan.FREE])
    return {"limits": plan_def["limits"], "features": plan_def["features"]}


def get_plan_info(plan: BillingPlan) -> Dict[str, Any]:
    """
    Get full plan information.

    Args:
        plan: Billing plan

    Returns:
        Dictionary with all plan details
    """
    return PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS[BillingPlan.FREE])


def check_limit(entitlement: Dict[str, Any], limit_key: str, current_value: int) -> bool:
    """
    Check if current value is within plan limit.

    Args:
        entitlement: Entitlement dictionary
        limit_key: Limit key to check (e.g., "max_users")
        current_value: Current value to check

    Returns:
        True if within limit, False if exceeded
    """
    limits = entitlement.get("limits", {})
    max_value = limits.get(limit_key, 0)

    # -1 means unlimited
    if max_value == -1:
        return True

    return current_value <= max_value


def check_feature(entitlement: Dict[str, Any], feature_key: str) -> bool:
    """
    Check if feature is enabled in plan.

    Args:
        entitlement: Entitlement dictionary
        feature_key: Feature key to check (e.g., "integrations_enabled")

    Returns:
        True if feature is enabled
    """
    features = entitlement.get("features", {})
    return features.get(feature_key, False)
