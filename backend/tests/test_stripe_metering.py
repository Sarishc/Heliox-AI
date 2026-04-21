"""Tests for Stripe metering export service."""

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.billing import TeamSubscription, BillingPlan
from app.models.usage import UsageDailyRollup, UsageEventType
from app.models.stripe_meter_export import StripeMeterExport
from app.services.stripe_metering import (
    export_usage_to_stripe,
    _teams_eligible_for_metering,
    _make_identifier,
)


@pytest.fixture
def paid_team_with_subscription(db_session: Session) -> Team:
    """Team with active paid subscription and stripe_customer_id."""
    team = Team(name="Paid Team")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)

    sub = TeamSubscription(
        team_id=team.id,
        stripe_customer_id="cus_test_paid123",
        stripe_subscription_id="sub_test_123",
        status="active",
        plan=BillingPlan.STARTER,
    )
    db_session.add(sub)
    db_session.commit()
    return team


@pytest.fixture
def free_team_no_subscription(db_session: Session) -> Team:
    """Team without paid subscription (no metering)."""
    team = Team(name="Free Team")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


@pytest.fixture
def team_with_subscription_no_customer(db_session: Session) -> Team:
    """Team with subscription but null stripe_customer_id (edge case)."""
    team = Team(name="No Customer Team")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    # Create subscription record without stripe_customer_id - use a minimal one
    # TeamSubscription requires stripe_customer_id (nullable=False), so we can't create one without it.
    # Instead use a canceled/inactive subscription - eligible filter excludes it
    sub = TeamSubscription(
        team_id=team.id,
        stripe_customer_id="cus_test_inactive",
        stripe_subscription_id="sub_inactive",
        status="canceled",  # Not in ACTIVE_STATUSES
        plan=BillingPlan.STARTER,
    )
    db_session.add(sub)
    db_session.commit()
    return team


def test_teams_eligible_for_metering_includes_paid_active(db_session: Session, paid_team_with_subscription: Team):
    """Eligible teams have active paid subscription and stripe_customer_id."""
    eligible = _teams_eligible_for_metering(db_session)
    assert paid_team_with_subscription.id in eligible


def test_teams_eligible_excludes_free_team(db_session: Session, free_team_no_subscription: Team):
    """Teams without subscription are not eligible."""
    eligible = _teams_eligible_for_metering(db_session)
    assert free_team_no_subscription.id not in eligible


def test_teams_eligible_excludes_canceled_subscription(db_session: Session, team_with_subscription_no_customer: Team):
    """Teams with canceled subscription are not eligible."""
    eligible = _teams_eligible_for_metering(db_session)
    assert team_with_subscription_no_customer.id not in eligible


def test_make_identifier_format():
    """Identifier is deterministic and under 100 chars."""
    from uuid import UUID

    team_id = UUID("00000000-0000-0000-0000-000000000001")
    ident = _make_identifier(team_id, date(2024, 1, 15), "api_request")
    assert ident.startswith("heliox_")
    assert "2024-01-15" in ident
    assert "api_request" in ident
    assert len(ident) <= 100


def test_export_dry_run_does_not_call_stripe(
    db_session: Session,
    paid_team_with_subscription: Team,
    monkeypatch,
):
    """Dry run does not invoke Stripe API."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="heliox_api_requests",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date.today() - timedelta(days=1)
    db_session.add(
        UsageDailyRollup(
            team_id=paid_team_with_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=50,
        )
    )
    db_session.commit()

    with patch("app.services.stripe_metering.stripe") as mock_stripe:
        result = export_usage_to_stripe(db_session, export_date, dry_run=True)
        mock_stripe.billing.MeterEvent.create.assert_not_called()

    assert result["exported"] == 1
    assert result["failed"] == 0
    # No StripeMeterExport records in dry run
    count = db_session.query(StripeMeterExport).count()
    assert count == 0


def test_export_skips_teams_without_billing_linkage(
    db_session: Session,
    free_team_no_subscription: Team,
    monkeypatch,
):
    """Teams without subscription are skipped (no export)."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="heliox_api_requests",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date.today() - timedelta(days=1)
    db_session.add(
        UsageDailyRollup(
            team_id=free_team_no_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=100,
        )
    )
    db_session.commit()

    result = export_usage_to_stripe(db_session, export_date, dry_run=True)
    # Eligible is empty, so no rollups are processed (eligible filter excludes free team)
    assert result["exported"] == 0
    assert result["skipped"] >= 0


def test_export_idempotent_skips_already_succeeded(
    db_session: Session,
    paid_team_with_subscription: Team,
    monkeypatch,
):
    """Second export for same (team, date, event_type) skips if already succeeded."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="heliox_api_requests",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date.today() - timedelta(days=1)
    db_session.add(
        UsageDailyRollup(
            team_id=paid_team_with_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=50,
        )
    )
    db_session.commit()

    with patch("app.services.stripe_metering.stripe") as mock_stripe:
        mock_stripe.billing.MeterEvent.create.return_value = MagicMock()
        result1 = export_usage_to_stripe(db_session, export_date, dry_run=False)
        assert result1["exported"] == 1
        assert mock_stripe.billing.MeterEvent.create.call_count == 1

        result2 = export_usage_to_stripe(db_session, export_date, dry_run=False)
        assert result2["skipped"] >= 1  # Skipped due to existing succeeded
        assert mock_stripe.billing.MeterEvent.create.call_count == 1  # No second call


def test_export_retries_failed_records(
    db_session: Session,
    paid_team_with_subscription: Team,
    monkeypatch,
):
    """Failed exports can be retried; only succeeded are skipped."""
    import stripe

    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="heliox_api_requests",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date.today() - timedelta(days=1)
    db_session.add(
        UsageDailyRollup(
            team_id=paid_team_with_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=50,
        )
    )
    db_session.commit()

    with patch("app.services.stripe_metering.stripe") as mock_stripe:
        mock_stripe.billing.MeterEvent.create.side_effect = stripe.StripeError("API error")
        result1 = export_usage_to_stripe(db_session, export_date, dry_run=False)
        assert result1["failed"] == 1
        assert result1["exported"] == 0

        # Retry should attempt again (status was failed, not succeeded)
        mock_stripe.billing.MeterEvent.create.side_effect = None
        mock_stripe.billing.MeterEvent.create.return_value = MagicMock()
        result2 = export_usage_to_stripe(db_session, export_date, dry_run=False)
        assert result2["exported"] == 1
        assert result2["failed"] == 0


def test_export_skips_when_meter_name_empty(
    db_session: Session,
    paid_team_with_subscription: Team,
    monkeypatch,
):
    """Event types with empty STRIPE_METER_* config are skipped."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="",  # Empty = skip
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date.today() - timedelta(days=1)
    db_session.add(
        UsageDailyRollup(
            team_id=paid_team_with_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=50,
        )
    )
    db_session.commit()

    with patch("app.services.stripe_metering.stripe") as mock_stripe:
        result = export_usage_to_stripe(db_session, export_date, dry_run=False)
        mock_stripe.billing.MeterEvent.create.assert_not_called()
    assert result["skipped"] >= 1


def test_export_no_stripe_key_returns_early(
    db_session: Session,
    paid_team_with_subscription: Team,
    monkeypatch,
):
    """When STRIPE_SECRET_KEY is empty, export returns early."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="",
            STRIPE_METER_API_REQUESTS="heliox_api",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    result = export_usage_to_stripe(db_session, date.today(), dry_run=False)
    assert result["exported"] == 0
    assert "Stripe not configured" in result["errors"]


def test_export_maps_rollup_to_meter_payload(
    db_session: Session,
    paid_team_with_subscription: Team,
    monkeypatch,
):
    """Correct event_name, payload (stripe_customer_id, value), and identifier sent to Stripe."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="heliox_api_requests",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date(2024, 6, 15)
    db_session.add(
        UsageDailyRollup(
            team_id=paid_team_with_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=100,
        )
    )
    db_session.commit()

    with patch("app.services.stripe_metering.stripe") as mock_stripe:
        mock_stripe.billing.MeterEvent.create.return_value = MagicMock()
        export_usage_to_stripe(db_session, export_date, dry_run=False)

        call_kwargs = mock_stripe.billing.MeterEvent.create.call_args[1]
        assert call_kwargs["event_name"] == "heliox_api_requests"
        assert call_kwargs["payload"]["stripe_customer_id"] == "cus_test_paid123"
        assert call_kwargs["payload"]["value"] == 100
        assert call_kwargs["identifier"].startswith("heliox_")
        assert "cus_" not in str(call_kwargs.get("identifier", ""))  # No secrets in identifier


def test_export_tenant_isolation(
    db_session: Session,
    paid_team_with_subscription: Team,
    free_team_no_subscription: Team,
    monkeypatch,
):
    """Only eligible (paid) team's usage is exported; free team's usage is not sent."""
    monkeypatch.setattr(
        "app.services.stripe_metering.get_settings",
        lambda: MagicMock(
            STRIPE_SECRET_KEY="sk_test_123",
            STRIPE_METER_API_REQUESTS="heliox_api_requests",
            STRIPE_METER_INGESTION="",
            STRIPE_METER_GPU_NODES="",
            STRIPE_METER_SEATS="",
        ),
    )

    export_date = date.today() - timedelta(days=1)
    db_session.add(
        UsageDailyRollup(
            team_id=paid_team_with_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=10,
        )
    )
    db_session.add(
        UsageDailyRollup(
            team_id=free_team_no_subscription.id,
            date=export_date,
            event_type=UsageEventType.API_REQUEST,
            total_quantity=999,
        )
    )
    db_session.commit()

    with patch("app.services.stripe_metering.stripe") as mock_stripe:
        mock_stripe.billing.MeterEvent.create.return_value = MagicMock()
        result = export_usage_to_stripe(db_session, export_date, dry_run=False)

    # Only paid team exported; free team has no subscription so not in eligible, rollup skipped
    assert result["exported"] == 1
    call = mock_stripe.billing.MeterEvent.create.call_args[1]
    assert call["payload"]["value"] == 10  # Paid team's 10, not 999
