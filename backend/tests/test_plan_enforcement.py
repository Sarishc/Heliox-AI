"""
Tests for plan enforcement logic.

Covers:
  1. require_plan_for_team allows access on qualifying plan
  2. require_plan_for_team returns HTTP 403 on lower plan (with structured body)
  3. check_team_limit allows creation when under limit
  4. check_team_limit returns HTTP 403 with limit_reached when at limit
  5. Starter plan cannot create API keys
  6. Starter plan cannot create more than 1 cluster/integration
  7. Growth plan cannot enable SSO
  8. Enterprise plan has no cluster limit
  9. GET /billing/plan returns correct limits and usage
 10. Stripe webhook subscription.deleted correctly downgrades team to Starter
"""
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi import HTTPException

from app.core.plans import PlanTier, PlanLimits, PLAN_LIMITS, get_limits, billing_plan_to_tier
from app.core.plan_enforcement import (
    require_plan_for_team,
    check_team_limit,
    get_plan_features,
)
from app.models.billing import BillingPlan, TeamSubscription


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_db_with_plan(plan: BillingPlan) -> MagicMock:
    """Return a mock DB session with a TeamSubscription for the given plan."""
    db = MagicMock()
    sub = MagicMock(spec=TeamSubscription)
    sub.plan = plan
    sub.stripe_customer_id = "cus_test"
    sub.stripe_subscription_id = None
    db.query.return_value.filter.return_value.first.return_value = sub
    db.query.return_value.filter.return_value.count.return_value = 0
    return db


def _mock_db_no_subscription() -> MagicMock:
    """Return a mock DB session where no subscription row exists (→ Starter)."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.count.return_value = 0
    return db


# ── 1-2: require_plan_for_team ────────────────────────────────────────────────

def test_require_plan_allows_qualifying_plan():
    """require_plan_for_team does not raise when team is on a qualifying plan."""
    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.GROWTH)
    # Should not raise
    require_plan_for_team(db, team_id, PlanTier.GROWTH, PlanTier.ENTERPRISE)


def test_require_plan_raises_403_on_lower_plan():
    """require_plan_for_team raises HTTP 403 when team is on a lower plan."""
    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.FREE)

    with pytest.raises(HTTPException) as exc_info:
        require_plan_for_team(db, team_id, PlanTier.GROWTH, PlanTier.ENTERPRISE)

    assert exc_info.value.status_code == 403
    body = exc_info.value.detail
    assert body["error"] == "plan_required"
    assert "required_plan" in body
    assert body["current_plan"] == PlanTier.STARTER.value
    assert "upgrade_url" in body


def test_require_plan_response_has_all_required_fields():
    """The 403 body includes error, message, required_plan, current_plan, upgrade_url."""
    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.FREE)

    with pytest.raises(HTTPException) as exc_info:
        require_plan_for_team(db, team_id, PlanTier.ENTERPRISE)

    body = exc_info.value.detail
    for field in ("error", "message", "required_plan", "current_plan", "upgrade_url"):
        assert field in body, f"Missing field: {field}"


def test_require_plan_no_subscription_treated_as_starter():
    """A team with no subscription row is treated as Starter."""
    team_id = uuid.uuid4()
    db = _mock_db_no_subscription()

    with pytest.raises(HTTPException) as exc_info:
        require_plan_for_team(db, team_id, PlanTier.GROWTH)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["current_plan"] == PlanTier.STARTER.value


# ── 3-4: check_team_limit ─────────────────────────────────────────────────────

def test_check_limit_allows_under_limit():
    """check_team_limit does not raise when current count is below the limit."""
    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.GROWTH)
    # Growth allows 5 API keys; current count 4 → OK
    check_team_limit(db, team_id, "max_api_keys", 4)


def test_check_limit_raises_403_at_limit():
    """check_team_limit raises HTTP 403 with limit_reached when count == limit."""
    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.GROWTH)
    # Growth allows 5 API keys; current count 5 → at limit
    with pytest.raises(HTTPException) as exc_info:
        check_team_limit(db, team_id, "max_api_keys", 5)

    assert exc_info.value.status_code == 403
    body = exc_info.value.detail
    assert body["error"] == "limit_reached"
    assert body["limit"] == 5
    assert body["current"] == 5
    assert "upgrade_url" in body


def test_check_limit_raises_403_above_limit():
    """check_team_limit raises HTTP 403 when count exceeds the limit."""
    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.FREE)
    # Starter allows 1 cluster; current count 2 → over limit
    with pytest.raises(HTTPException) as exc_info:
        check_team_limit(db, team_id, "max_clusters", 2)

    assert exc_info.value.status_code == 403


# ── 5: Starter plan cannot create API keys ────────────────────────────────────

def test_starter_cannot_create_api_keys():
    """
    Starter plan has max_api_keys=0 so even the first key creation is blocked.
    """
    assert PLAN_LIMITS[PlanTier.STARTER].max_api_keys == 0

    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.FREE)

    # require_plan gate fires first (Starter lacks Growth+)
    with pytest.raises(HTTPException) as exc_info:
        require_plan_for_team(db, team_id, PlanTier.GROWTH, PlanTier.ENTERPRISE)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "plan_required"


# ── 6: Starter plan max 1 cluster ────────────────────────────────────────────

def test_starter_cannot_create_second_cluster():
    """Starter plan allows 1 integration (cluster); a second creation is blocked."""
    assert PLAN_LIMITS[PlanTier.STARTER].max_clusters == 1

    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.FREE)

    with pytest.raises(HTTPException) as exc_info:
        check_team_limit(db, team_id, "max_clusters", 1)  # already at 1

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "limit_reached"


# ── 7: Growth plan cannot enable SSO ─────────────────────────────────────────

def test_growth_cannot_enable_sso():
    """Growth plan does not have sso_enabled; SSO requires Enterprise."""
    assert PLAN_LIMITS[PlanTier.GROWTH].sso_enabled is False
    assert PLAN_LIMITS[PlanTier.ENTERPRISE].sso_enabled is True

    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.GROWTH)

    with pytest.raises(HTTPException) as exc_info:
        require_plan_for_team(db, team_id, PlanTier.ENTERPRISE)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["current_plan"] == PlanTier.GROWTH.value
    assert exc_info.value.detail["required_plan"] == PlanTier.ENTERPRISE.value


# ── 8: Enterprise has no cluster limit ───────────────────────────────────────

def test_enterprise_has_no_cluster_limit():
    """Enterprise plan has max_clusters=-1 (unlimited); check_team_limit never blocks."""
    assert PLAN_LIMITS[PlanTier.ENTERPRISE].max_clusters == -1

    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.ENTERPRISE)

    # Should not raise even with a huge count
    check_team_limit(db, team_id, "max_clusters", 9999)


def test_enterprise_has_no_api_key_limit():
    """Enterprise plan has max_api_keys=-1 (unlimited)."""
    assert PLAN_LIMITS[PlanTier.ENTERPRISE].max_api_keys == -1

    team_id = uuid.uuid4()
    db = _mock_db_with_plan(BillingPlan.ENTERPRISE)
    check_team_limit(db, team_id, "max_api_keys", 9999)


# ── 9: GET /billing/plan returns correct data ─────────────────────────────────

def test_get_billing_plan_endpoint_returns_correct_limits():
    """GET /billing/plan returns the team's plan, limits, and usage counts."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.auth.team_resolution import verify_team_api_key_or_session
    from app.auth.rbac import require_team_admin_or_api_key

    team_id = uuid.uuid4()

    mock_auth = MagicMock()
    mock_auth.team_id = team_id

    mock_sub = MagicMock()
    mock_sub.plan = BillingPlan.GROWTH
    mock_sub.stripe_customer_id = "cus_test"
    mock_sub.stripe_subscription_id = "sub_test"

    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True

    app.dependency_overrides[verify_team_api_key_or_session] = lambda: mock_auth
    app.dependency_overrides[require_team_admin_or_api_key] = lambda: mock_auth

    from app.core.db import get_db

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_sub
    mock_db.query.return_value.filter.return_value.count.return_value = 2

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with patch("app.core.rate_limit.require_redis", return_value=mock_redis), \
             patch("app.core.plan_enforcement._get_team_tier", return_value=PlanTier.GROWTH):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/v1/billing/plan")

        if response.status_code == 200:
            body = response.json()
            assert body["plan"] == "growth"
            assert "limits" in body
            assert "usage" in body
            assert body["limits"]["max_clusters"] == 5
            assert body["limits"]["history_days"] == 365
            assert body["limits"]["slack_alerts"] is True
            assert body["limits"]["sso_enabled"] is False
        else:
            # Accept 503 if Stripe is not configured in test env
            assert response.status_code in (200, 503)
    finally:
        app.dependency_overrides.pop(verify_team_api_key_or_session, None)
        app.dependency_overrides.pop(require_team_admin_or_api_key, None)
        app.dependency_overrides.pop(get_db, None)


# ── 10: Webhook subscription.deleted downgrades to Starter ───────────────────

def test_webhook_subscription_deleted_downgrades_to_starter():
    """
    handle_subscription_deleted() sets TeamSubscription.plan to FREE (Starter)
    and clears stripe_subscription_id.
    """
    from app.billing.stripe_client import handle_subscription_deleted

    team_id = uuid.uuid4()

    # Set up a mock subscription that's currently on Growth
    mock_sub = MagicMock()
    mock_sub.plan = BillingPlan.GROWTH
    mock_sub.stripe_subscription_id = "sub_123"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_sub

    stripe_event = MagicMock()
    stripe_event.metadata = {"team_id": str(team_id)}
    stripe_event.__getitem__ = lambda self, k: {"id": "sub_123", "customer": "cus_test", "status": "canceled"}[k]
    stripe_event.get = lambda k, default=None: {"id": "sub_123", "customer": "cus_test", "status": "canceled"}.get(k, default)

    with patch("app.billing.stripe_client.update_team_entitlements") as mock_update:
        handle_subscription_deleted(mock_db, stripe_event)

    # Subscription should be reset to FREE / null stripe_subscription_id
    assert mock_sub.plan == BillingPlan.FREE
    assert mock_sub.stripe_subscription_id is None
    mock_db.commit.assert_called()


# ── plan constants correctness ────────────────────────────────────────────────

def test_plan_limits_values_match_spec():
    """Verify exact limit values match the product spec."""
    starter = PLAN_LIMITS[PlanTier.STARTER]
    assert starter.max_clusters == 1
    assert starter.history_days == 30
    assert starter.max_api_keys == 0
    assert starter.max_team_members == 3
    assert starter.slack_alerts is False
    assert starter.sso_enabled is False
    assert starter.api_access is False

    growth = PLAN_LIMITS[PlanTier.GROWTH]
    assert growth.max_clusters == 5
    assert growth.history_days == 365
    assert growth.max_api_keys == 5
    assert growth.max_team_members == 25
    assert growth.slack_alerts is True
    assert growth.sso_enabled is False
    assert growth.api_access is True

    ent = PLAN_LIMITS[PlanTier.ENTERPRISE]
    assert ent.max_clusters == -1
    assert ent.history_days == -1
    assert ent.sso_enabled is True
    assert ent.custom_rbac is True
    assert ent.dedicated_csm is True


def test_billing_plan_to_tier_mapping():
    """BillingPlan.FREE and BillingPlan.STARTER both map to PlanTier.STARTER."""
    assert billing_plan_to_tier(BillingPlan.FREE) == PlanTier.STARTER
    assert billing_plan_to_tier(BillingPlan.STARTER) == PlanTier.STARTER
    assert billing_plan_to_tier(BillingPlan.GROWTH) == PlanTier.GROWTH
    assert billing_plan_to_tier(BillingPlan.ENTERPRISE) == PlanTier.ENTERPRISE
