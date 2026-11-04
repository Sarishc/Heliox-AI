"""
Regressions for the Step 6F corrective review, on real PostgreSQL in one disposable database per module.

Each failed-verification case asserts the database, not only the result: no final coverage, no confirmed zero,
no checkpoint. Provider responses come from fake clients; nothing here proves real provider behaviour.
"""

import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_ledger_shadow_orchestration_postgres import (  # noqa: F401
    A,
    ALICE,
    B,
    ENABLED,
    AwsClients,
    GcpClient,
    Rig,
    WorkerCrash,
    account_id,
    checkpoint,
    engine,
    fetched_at,
    legacy_untouched,
    line,
    metrics,
    money,
    q,
    records,
    rig_with,
    spec,
    staged,
    total,
)

from app.integrations.ledger.aws import AwsCostExplorerAdapter
from app.integrations.ledger.azure import AzureCostManagementAdapter
from app.integrations.ledger.base import VERIFIED, DateWindow, FetchIncomplete, ScopeVerdict, SourcePage
from app.integrations.ledger.gcp import GcpBillingExportAdapter
from app.services.cost_ledger import CostLedgerService
from app.services.ledger_shadow.activation import ShadowActivationRefused
from app.services.ledger_shadow.coverage import stream_coverage
from app.services.ledger_shadow.enrollment import EnrollmentRefused, enroll_connection, revoke_connection
from app.services.ledger_shadow.inventory import configure_inventory
from app.services.ledger_shadow.orchestrator import ShadowSyncOrchestrator
from app.services.ledger_shadow.staging import MissingPage, StagingConflict, stage_page

DAY = date(2026, 3, 2)
PAYER, LINKED = "111111111111", "222222222222"


def new_team(engine, mode="shadow"):
    team = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id, name) VALUES (:t, :n)"), {"t": team, "n": f"t-{team.hex[:8]}"})
        if mode:
            c.execute(
                text("INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:t, :m)"),
                {"t": team, "m": mode},
            )
    return team


def window_of(day, days=1):
    return DateWindow(day, day + timedelta(days))


def completeness(engine, team, day, account):
    with Session(engine) as s:
        return [c for c in CostLedgerService(s).coverage_completeness(team, [day]) if c.usage_account == account]


def assert_nothing_known(engine, team, day, sid, account, run_id):
    """Failed verification leaves no coverage, no confirmed zero and no checkpoint."""
    assert (
        q(
            engine,
            "SELECT count(*) FROM cost_source_coverage WHERE team_id = :t AND usage_account = :a",
            t=team,
            a=account,
        )
        == 0
    )
    assert q(engine, "SELECT count(*) FROM cost_source_stream_days WHERE stream_id = :s", s=sid) == 0
    assert q(engine, "SELECT count(*) FROM cost_source_stream_checkpoints WHERE stream_id = :s", s=sid) == 0
    assert records(engine, sid) == 0
    assert completeness(engine, team, day, account) == []
    assert staged(engine, run_id) == 0
    legacy_untouched(engine)


class Aws:
    """A payer's or member's view. Cost Explorer returns no groups, as it does for an account with no cost here."""

    def __init__(self, day, caller=PAYER, master=PAYER, members=None, amount=None, org_error=None):
        self.day, self.caller, self.master, self.amount, self.org_error = day, caller, master, amount, org_error
        self.members = members if members is not None else {PAYER: "ACTIVE", LINKED: "ACTIVE"}
        self.cost_calls = 0

    def __call__(self, service):
        return self

    def get_caller_identity(self):
        return {"Account": self.caller}

    def describe_organization(self):
        if self.org_error:
            raise self.org_error
        return {"Organization": {"MasterAccountId": self.master}}

    def list_accounts(self, **kwargs):
        return {
            "Accounts": [
                {"Id": i, "State": s, "JoinedTimestamp": datetime(2020, 1, 1, tzinfo=timezone.utc)}
                for i, s in self.members.items()
            ]
        }

    def get_dimension_values(self, **kwargs):
        return {"DimensionValues": []}

    def get_cost_and_usage(self, **kwargs):
        self.cost_calls += 1
        groups = []
        if self.amount:
            groups = [
                {"Keys": ["Amazon EC2", "Usage"], "Metrics": {"UnblendedCost": {"Amount": self.amount, "Unit": "USD"}}}
            ]
        return {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": self.day.isoformat(), "End": (self.day + timedelta(1)).isoformat()},
                    "Estimated": False,
                    "Total": {},
                    "Groups": groups,
                }
            ]
        }


def aws_adapter(accounts, client, payer=PAYER):
    return AwsCostExplorerAdapter(
        {"payer_account_id": payer, "linked_account_ids": list(accounts)}, client_factory=client
    )


class AccessDenied(Exception):
    response = {"Error": {"Code": "AccessDeniedException"}}


@pytest.mark.parametrize(
    "name,accounts,kwargs,code",
    [
        ("nonexistent", ["999999999999"], {}, "account_not_in_organization"),
        ("moved_out", [LINKED], {"members": {PAYER: "ACTIVE"}}, "account_not_in_organization"),
        ("suspended", [LINKED], {"members": {LINKED: "SUSPENDED"}}, "account_not_active"),
        ("unrelated_for_member", ["999999999999"], {"caller": LINKED}, "account_not_visible_to_caller"),
        ("payer_is_wrong", [LINKED], {"master": "888888888888"}, "payer_mismatch"),
        ("permissions_missing", [LINKED], {"org_error": AccessDenied()}, "payer_unverifiable"),
    ],
)
def test_aws_failed_scope_verification_can_never_be_a_zero(engine, name, accounts, kwargs, code):
    team = new_team(engine)
    client = Aws(DAY, **kwargs)
    rig = rig_with(engine, aws_adapter(accounts, client), team)
    run_id, result = rig.run(window_of(DAY))
    assert result.status == "failed"
    account = f"aws:acct:{accounts[0]}"
    assert client.cost_calls == 0  # refused before any cost query
    assert_nothing_known(engine, team, DAY, rig.streams[account], account, run_id)
    report = metrics(engine, run_id)["ledger"]["inventory"]
    assert report["scope_unverified"] == [account] and report["missing"] == [account] and report["published"] == []
    assert q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id)["stream_errors"] == {
        account: code
    }
    assert q(engine, "SELECT error_code FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id) == code


def test_aws_verified_account_with_no_cost_is_a_genuine_zero(engine):
    team = new_team(engine)
    rig = rig_with(engine, aws_adapter([LINKED], Aws(DAY)), team)
    run_id, result = rig.run(window_of(DAY))
    assert result.status == "published"
    [c] = completeness(engine, team, DAY, f"aws:acct:{LINKED}")
    assert (c.fetch_state, c.financial_state, c.converted_total_usd) == ("final", "complete", Decimal("0"))


GCP_BILLING = "0A1B2C-3D4E5F-6A7B8C"
EMPTY_EXPORT = datetime(2026, 10, 1, tzinfo=timezone.utc)


def gcp_adapter(projects, lookup, client=None):
    return GcpBillingExportAdapter(
        {
            "gcp_project_id": "billing-admin-1",
            "bigquery_dataset": "billing_export",
            "billing_export_table": "gcp_billing_export_v1",
            "billing_account_id": GCP_BILLING,
            "project_ids": list(projects),
        },
        client_factory=client or GcpClient([]),
        parameters=lambda v: v,
        project_billing_info=lookup,
        today=lambda: date(2026, 10, 1),
    )


@pytest.mark.parametrize(
    "answer,code",
    [
        (
            {"billingAccountName": "billingAccounts/FFFFFF-FFFFFF-FFFFFF", "billingEnabled": True},
            "project_on_other_billing_account",
        ),
        ({"billingAccountName": "", "billingEnabled": False}, "project_has_no_billing_account"),
        ({"billingAccountName": f"billingAccounts/{GCP_BILLING}", "billingEnabled": False}, "project_billing_disabled"),
    ],
)
def test_gcp_project_not_on_this_billing_account_is_never_zero(engine, answer, code):
    team = new_team(engine)
    rig = rig_with(engine, gcp_adapter(["other-project-1"], lambda p: answer), team)
    run_id, result = rig.run(window_of(DAY))
    assert result.status == "failed"
    account = "gcp:project:other-project-1"
    assert_nothing_known(engine, team, DAY, rig.streams[account], account, run_id)
    errors = q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id)["stream_errors"]
    assert errors[account] == code


def test_gcp_missing_export_data_is_not_a_zero_and_neither_is_a_caught_up_export(engine):
    team = new_team(engine)
    ok = {"billingAccountName": f"billingAccounts/{GCP_BILLING}", "billingEnabled": True}

    class Behind(GcpClient):
        def result(self):
            rows = super().result()
            if self.sql.startswith("SELECT MAX(export_time)"):
                rows.pages = iter([[{"last_export": datetime(2026, 1, 1, tzinfo=timezone.utc)}]])
            return rows

    behind = rig_with(engine, gcp_adapter(["quiet-project-1"], lambda p: ok, Behind([])), team)
    run_id = behind.orchestrator.create_run(team, behind.conn, window_of(DAY))
    assert behind.orchestrator.execute(run_id).reason.split(",")[0] == "export_behind_window"
    assert q(engine, "SELECT count(*) FROM cost_source_coverage WHERE team_id = :t", t=team) == 0

    team2 = new_team(engine)
    current = rig_with(engine, gcp_adapter(["quiet-project-1"], lambda p: ok), team2)
    run_id, result = current.run(window_of(DAY))
    assert result.status == "partial"
    assert completeness(engine, team2, DAY, "gcp:project:quiet-project-1") == []  # caught up, and still unknown
    assert metrics(engine, run_id)["ledger"]["inventory"]["unproven_days"]["gcp:project:quiet-project-1"] == [
        DAY.isoformat()
    ]


SUB = "33333333-3333-3333-3333-333333333333"


def azure_adapter(state_response, config=None, list_response=None):
    query_calls = []

    def handler(request):
        url = str(request.url)
        if request.method == "GET" and "billingSubscriptions" in url:
            return list_response
        if request.method == "GET":
            return state_response
        query_calls.append(url)
        return httpx.Response(
            200,
            json={
                "properties": {
                    "columns": [
                        {"name": n} for n in ("Cost", "CostUSD", "UsageDate", "ServiceName", "ChargeType", "Currency")
                    ],
                    "rows": [],
                }
            },
        )

    adapter = AzureCostManagementAdapter(
        {"subscription_ids": [SUB], **(config or {})},
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda f: "t",
        sleep=lambda s: None,
        today=lambda: date(2026, 10, 1),
    )
    return adapter, query_calls


@pytest.mark.parametrize(
    "response,config,listed,code",
    [
        (httpx.Response(404), None, None, "subscription_inaccessible"),
        (httpx.Response(403), None, None, "subscription_inaccessible"),
        (httpx.Response(200, json={"state": "Disabled"}), None, None, "subscription_not_active"),
        (httpx.Response(200, json={"state": "Deleted"}), None, None, "subscription_not_active"),
        (
            None,
            {"billing_account_id": "BA-1", "use_billing_account_scope": True},
            httpx.Response(200, json={"value": [{"properties": {"subscriptionId": "other"}}]}),
            "subscription_not_in_billing_scope",
        ),
        (
            None,
            {"billing_account_id": "BA-1", "use_billing_account_scope": True},
            httpx.Response(403),
            "billing_scope_unverifiable",
        ),
    ],
)
def test_azure_unproven_subscription_is_never_zero(engine, response, config, listed, code):
    team = new_team(engine)
    adapter, query_calls = azure_adapter(response, config, listed)
    if config:  # discovery uses the same query endpoint and would fail on these rows
        adapter.discover = lambda window: __import__("app.integrations.ledger.base", fromlist=["Discovery"]).Discovery(
            supported=False
        )
    rig = rig_with(engine, adapter, team)
    run_id, result = rig.run(window_of(DAY))
    assert result.status == "failed"
    account = f"azure:sub:{SUB}"
    assert query_calls == []
    assert_nothing_known(engine, team, DAY, rig.streams[account], account, run_id)
    assert q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id)["stream_errors"] == {
        account: code
    }


def test_azure_verified_subscription_with_no_cost_is_a_genuine_zero(engine):
    team = new_team(engine)
    adapter, _ = azure_adapter(httpx.Response(200, json={"state": "Enabled"}))
    rig = rig_with(engine, adapter, team)
    _, result = rig.run(window_of(DAY))
    assert result.status == "published"
    [c] = completeness(engine, team, DAY, f"azure:sub:{SUB}")
    assert (c.financial_state, c.converted_total_usd) == ("complete", Decimal("0"))


def test_a_failing_scope_lookup_verifies_nothing_and_retries(engine):
    account = account_id()
    rig = Rig(engine, {account: [[line(1, day=DAY)]]})

    def broken():
        raise RuntimeError("token=SECRET-in-exception")

    rig.adapter.verify_scope = broken
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(DAY))
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("retry", "scope_lookup_failed")
    assert rig.adapter.calls == 0
    assert "SECRET" not in str(metrics(engine, run_id))


def test_an_account_the_verifier_did_not_mention_is_unverified(engine):
    first, second = account_id(), account_id()
    day = DAY + timedelta(1)
    rig = Rig(
        engine,
        {first: [[line(1, day=day, bucket="unmentioned")]], second: [[line(2, day=day, bucket="unmentioned")]]},
        verdicts={first: VERIFIED},
    )
    run_id, result = rig.run(window_of(day))
    assert result.status == "partial"
    assert records(engine, rig.streams[second]) == 0
    assert money(total(engine, A, day, "unmentioned")) == (Decimal("1.00"), "complete")
    assert metrics(engine, run_id)["ledger"]["inventory"]["scope_unverified"] == [second]


# Cross-connection double counting


def test_two_payer_values_for_one_account_do_not_double_count(engine):
    """The original defect read $200 for a $100 bill."""
    team = new_team(engine)
    day = DAY + timedelta(2)
    real = rig_with(engine, aws_adapter([LINKED], Aws(day, amount="100")), team)
    # The second connection is configured with a payer AWS does not confirm
    claimed = rig_with(
        engine,
        aws_adapter(
            [LINKED], Aws(day, caller="777777777777", master="111111111111", amount="100"), payer="777777777777"
        ),
        team,
    )
    real_run = None
    # Both are bound, so the source is ambiguous before anything is published
    real_run, real_result = real.run(window_of(day))
    claimed_run, claimed_result = claimed.run(window_of(day))
    assert (real_result.status, claimed_result.status) == ("failed", "failed")
    account = f"aws:acct:{LINKED}"
    assert metrics(engine, real_run)["ledger"]["inventory"]["ambiguous"] == [account]
    assert total(engine, team, day, "ec2") is None
    assert q(engine, "SELECT count(*) FROM cost_source_records WHERE team_id = :t", t=team) == 0
    # Removing the wrong claim is the resolution; nothing was chosen automatically
    with real.sessions() as s, s.begin():
        s.execute(
            text("UPDATE cost_source_stream_bindings SET unbound_at = now() WHERE connection_id = :c"),
            {"c": claimed.conn},
        )
    _, result = real.run(window_of(day))
    assert result.status == "published"
    assert money(total(engine, team, day, "ec2")) == (Decimal("100.00"), "complete")


def test_a_payer_mismatch_alone_blocks_a_connection(engine):
    team = new_team(engine)
    day = DAY + timedelta(3)
    rig = rig_with(
        engine,
        aws_adapter([LINKED], Aws(day, caller="777777777777", master=PAYER, amount="100"), payer="777777777777"),
        team,
    )
    run_id, result = rig.run(window_of(day))
    assert result.status == "failed"
    assert q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id)["stream_errors"] == {
        f"aws:acct:{LINKED}": "payer_mismatch"
    }


def test_a_new_claim_makes_already_published_totals_incomplete_until_resolved(engine):
    day = DAY + timedelta(4)
    account = account_id()
    first = Rig(engine, {account: [[line(100, day=day, bucket="claim")]]}, specs=[spec(account, ba="aws:payer:1")])
    first.run(window_of(day))
    assert money(total(engine, A, day, "claim")) == (Decimal("100.00"), "complete")
    second = Rig(engine, {account: [[line(100, day=day, bucket="claim")]]}, specs=[spec(account, ba="aws:payer:2")])
    t = total(engine, A, day, "claim")
    assert (t.amount_usd, t.completeness, t.blocked) == (Decimal("100.00"), "incomplete", 1)
    [c] = completeness(engine, A, day, account)
    assert (c.financial_state, c.source_ambiguous) == ("incomplete", True)
    run_id, result = second.run(window_of(day))
    assert result.status == "failed"
    assert records(engine, second.streams[account]) == 0
    with second.sessions() as s, s.begin():
        s.execute(
            text("UPDATE cost_source_stream_bindings SET unbound_at = now() WHERE connection_id = :c"),
            {"c": second.conn},
        )
    assert money(total(engine, A, day, "claim")) == (Decimal("100.00"), "complete")


def test_a_claim_arriving_during_a_fetch_stops_publication(engine):
    day = DAY + timedelta(5)
    account = account_id()

    def rival_appears():
        Rig(engine, {account: []}, specs=[spec(account, ba="aws:payer:rival")])

    rig = Rig(
        engine,
        {account: [rival_appears, [line(100, day=day, bucket="rival")]]},
        specs=[spec(account, ba="aws:payer:mine")],
    )
    run_id, result = rig.run(window_of(day))
    assert result.status == "failed"
    assert records(engine, rig.streams[account]) == 0
    assert (
        q(engine, "SELECT error_code FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id)
        == "source_identity_ambiguous"
    )


def test_payer_and_member_views_of_one_bill_count_once_and_keep_explicit_authority(engine):
    team = new_team(engine)
    day = DAY + timedelta(6)
    account = f"aws:acct:{LINKED}"
    payer = rig_with(engine, aws_adapter([LINKED], Aws(day, amount="100")), team)
    member = rig_with(engine, aws_adapter([LINKED], Aws(day, caller=LINKED, amount="100")), team)
    assert payer.adapter.streams()[0].billing_account == member.adapter.streams()[0].billing_account
    with payer.sessions() as s, s.begin():
        CostLedgerService(s).set_authority(
            team_id=team,
            provider="aws",
            billing_account=f"aws:payer:{PAYER}",
            usage_account=account,
            stream_id=payer.streams[account],
            actor_user_id=ALICE,
            reason="payer is the invoice",
        )
    member_run, member_result = member.run(window_of(day))
    assert member_result.status == "published"
    assert metrics(engine, member_run)["ledger"]["inventory"]["witness"] == [account]
    t = total(engine, team, day, "ec2")
    assert (t.amount_usd, t.completeness) == (None, "incomplete")  # the authority has not published: not a zero
    payer.run(window_of(day))
    assert money(total(engine, team, day, "ec2")) == (Decimal("100.00"), "complete")
    assert q(engine, "SELECT stream_id FROM cost_source_authority WHERE team_id = :t", t=team) == payer.streams[account]
    assert q(engine, "SELECT count(*) FROM cost_source_conflicts WHERE team_id = :t", t=team) == 0


def test_the_same_account_in_another_team_is_not_ambiguous(engine):
    day = DAY + timedelta(7)
    account = account_id()
    mine = Rig(engine, {account: [[line(5, day=day, bucket="iso")]]}, specs=[spec(account, ba="aws:payer:1")])
    theirs = Rig(engine, {account: [[line(9, day=day, bucket="iso")]]}, team=B, specs=[spec(account, ba="aws:payer:2")])
    assert mine.run(window_of(day))[1].status == "published"
    assert theirs.run(window_of(day))[1].status == "published"
    assert money(total(engine, A, day, "iso")) == (Decimal("5.00"), "complete")
    assert money(total(engine, B, day, "iso")) == (Decimal("9.00"), "complete")


# Checkpoint semantics


def coverage(rig, account, start, days):
    with rig.sessions() as s:
        return stream_coverage(s, rig.streams[account], window_of(start, days))


def test_first_window_never_implies_earlier_history(engine):
    day, account = DAY + timedelta(10), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    rig.run(window_of(day))
    sid = rig.streams[account]
    assert checkpoint(engine, sid) is None
    assert fetched_at(engine, sid) is not None
    earlier = coverage(rig, account, day - timedelta(3), 4)
    assert earlier.final_through is None  # asked from an earlier start, nothing is proven
    assert earlier.missing == [day - timedelta(3), day - timedelta(2), day - timedelta(1)]
    from_first = coverage(rig, account, day, 1)
    assert (from_first.final_through, from_first.financially_complete_through) == (day, day)


def test_a_gap_and_out_of_order_windows(engine):
    start, account = DAY + timedelta(15), account_id()
    rig = Rig(engine, {account: []})
    third = start + timedelta(2)
    rig.run(window_of(third), {account: [[line(3, day=third)]]})  # the third day first
    assert coverage(rig, account, start, 3).final_through is None
    rig.run(window_of(start), {account: [[line(1, day=start)]]})
    report = coverage(rig, account, start, 3)
    assert report.final_through == start  # stops at the gap, even though a later day is known
    assert report.missing == [start + timedelta(1)]
    middle = start + timedelta(1)
    rig.run(window_of(middle), {account: [[line(2, day=middle)]]})
    assert coverage(rig, account, start, 3).final_through == third
    assert checkpoint(engine, rig.streams[account]) is None


def test_estimated_days_corrections_and_financial_state_stay_separate(engine):
    start, account = DAY + timedelta(20), account_id()
    second = start + timedelta(1)
    rig = Rig(engine, {account: []})
    window = window_of(start, 2)
    rig.run(window, {account: [[line(5, day=start), line(9, day=second, est=True)]]})
    report = coverage(rig, account, start, 2)
    assert report.final_through == start
    assert [d.provider_state for d in report.days] == ["final", "estimated"]
    assert [d.financial_state for d in report.days] == ["complete", "estimated"]
    rig.run(window, {account: [[line(5, day=start), line(9, day=second)]]})
    assert coverage(rig, account, start, 2).final_through == second
    # A later correction back to estimated is reported as it is now; no stored value keeps claiming more
    rig.run(window, {account: [[line(5, day=start), line(8, day=second, est=True)]]})
    assert coverage(rig, account, start, 2).final_through == start
    # A final fetch with unconverted cost is fetch-final but not financially complete
    rig.run(window, {account: [[line(5, day=start, cur="EUR"), line(8, day=second)]]})
    report = coverage(rig, account, start, 2)
    assert (report.final_through, report.financially_complete_through) == (second, None)
    assert report.days[0].financial_state == "incomplete"


def test_coverage_for_witness_conflict_and_unverified_streams(engine):
    day, account = DAY + timedelta(25), account_id()
    payer = Rig(engine, {account: [[line(100, day=day, bucket="wit")]]})
    member = Rig(engine, {account: [[line(95, day=day, bucket="wit")]]}, specs=[spec(account, vantage="aws:caller:m")])
    payer.run(window_of(day))
    member.run(window_of(day))
    assert coverage(payer, account, day, 1).days[0].financial_state == "incomplete"  # an open conflict
    assert coverage(member, account, day, 1).days[0].financial_state == "not_authoritative"
    unverified_account = account_id()
    blocked = Rig(
        engine,
        {unverified_account: [[line(1, day=day)]]},
        verdicts={unverified_account: ScopeVerdict(False, "account_not_in_organization")},
    )
    blocked.run(window_of(day))
    report = coverage(blocked, unverified_account, day, 1)
    assert (report.final_through, report.days[0].fetched, report.days[0].financial_state) == (None, False, "unknown")
    assert fetched_at(engine, blocked.streams[unverified_account]) is None


# Connection eligibility


@pytest.mark.parametrize(
    "change,code",
    [
        ("status = 'disabled'", "connection_disabled"),
        ("status = 'pending'", "connection_pending"),
        ("status = 'error'", "connection_error"),
        ("deleted_at = now()", "connection_deleted"),
        ("config_encrypted = ''", "credentials_missing"),
    ],
)
def test_ineligible_connections_are_refused_before_anything_happens(engine, change, code):
    day, account = DAY + timedelta(30), account_id()
    rig = Rig(engine, {account: [[line(7, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
    with engine.begin() as c:
        c.execute(text(f"UPDATE integration_connections SET {change} WHERE id = :c"), {"c": rig.conn})
    calls_before = rig.adapter.calls
    called = []
    rig.adapter.streams = lambda: called.append("streams") or rig.adapter.specs
    with pytest.raises(ShadowActivationRefused) as err:
        rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
    assert err.value.code == code
    # Between run creation and worker execution
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("failed", code)
    assert called == [] and rig.adapter.calls == calls_before  # no provider call of any kind
    assert rig.run_state(run_id) == "failed/failed/0"
    assert (records(engine, rig.streams[account]), staged(engine, run_id)) == (0, 0)
    assert q(engine, "SELECT count(*) FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id) == 0
    assert (
        q(engine, "SELECT count(*) FROM cost_source_stream_checkpoints WHERE stream_id = :s", s=rig.streams[account])
        == 0
    )


def test_another_tenants_connection_is_refused(engine):
    day, account = DAY + timedelta(31), account_id()
    rig = Rig(engine, {account: [[line(7, day=day)]]})
    with pytest.raises(ShadowActivationRefused) as err:
        rig.orchestrator.create_run(B, rig.conn, window_of(day))
    assert err.value.code == "connection_not_owned"
    run_id = rig.orchestrator.create_run(A, rig.conn, window_of(day))
    with engine.begin() as c:  # the run names a different owner than the connection now has
        c.execute(
            text("UPDATE integration_sync_runs SET metrics_json = CAST(:m AS json) WHERE id = :r"),
            {
                "m": json.dumps(
                    {"ledger": {"team_id": str(B), "manifest": metrics(engine, run_id)["ledger"]["manifest"]}}
                ),
                "r": run_id,
            },
        )
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("failed", "connection_not_owned")
    assert rig.adapter.calls == 0


@pytest.mark.parametrize("change", ["status = 'disabled'", "deleted_at = now()"])
def test_a_connection_disabled_during_a_fetch_publishes_nothing(engine, change):
    day, account = DAY + timedelta(32), account_id()

    def disable():
        with engine.begin() as c:
            c.execute(text(f"UPDATE integration_connections SET {change} WHERE id = :c"), {"c": rig.conn})

    rig = Rig(engine, {account: [disable, [line(7, day=day, bucket="mid")]]})
    run_id, result = rig.run(window_of(day))
    assert result.status == "failed"
    assert records(engine, rig.streams[account]) == 0
    assert staged(engine, run_id) == 0
    assert rig.lease().startswith("-/")


def test_an_unbound_stream_during_a_fetch_publishes_nothing(engine):
    day, account = DAY + timedelta(33), account_id()

    def unbind():
        with engine.begin() as c:
            c.execute(
                text("UPDATE cost_source_stream_bindings SET unbound_at = now() WHERE connection_id = :c"),
                {"c": rig.conn},
            )

    rig = Rig(engine, {account: [unbind, [line(7, day=day, bucket="unbound")]]})
    run_id, result = rig.run(window_of(day))
    assert (result.status, result.reason) == ("failed", "stream_unbound")
    assert records(engine, rig.streams[account]) == 0


def test_unreadable_credentials_end_the_run_without_a_provider_call(engine):
    day, account = DAY + timedelta(34), account_id()
    rig = Rig(engine, {account: [[line(7, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
    real_factory = ShadowSyncOrchestrator(
        rig.sessions, policy=ENABLED
    )  # the default factory decrypts the stored config
    result = real_factory.execute(run_id)
    assert (result.status, result.reason) == ("failed", "credentials_unreadable")
    assert rig.run_state(run_id) == "failed/failed/0"


# Staging durability


def prepared(engine, day):
    account = account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
    with rig.sessions() as s, s.begin():
        CostLedgerService(s).acquire_lease(run_id, 1)
        s.execute(
            text(
                "INSERT INTO cost_sync_run_streams (sync_run_id, connection_id, attempt, team_id, stream_id, window_start, "
                "window_end, status) VALUES (:r, :c, 1, :t, :s, :a, :b, 'pending')"
            ),
            {"r": run_id, "c": rig.conn, "t": A, "s": rig.streams[account], "a": day, "b": day + timedelta(1)},
        )
    return rig, run_id, rig.streams[account]


def stage(rig, run_id, sid, page):
    with rig.sessions() as s, s.begin():
        stage_page(s, run_id, 1, sid, page)


def test_a_final_page_cannot_conceal_missing_pages(engine):
    day = DAY + timedelta(35)
    rig, run_id, sid = prepared(engine, day)
    stage(rig, run_id, sid, SourcePage(0, (line(1, day=day),)))
    with pytest.raises(MissingPage):
        stage(rig, run_id, sid, SourcePage(5, (line(2, day=day, svc="S3"),), is_last=True))
    assert staged(engine, run_id) == 1
    assert (
        q(engine, "SELECT status || '/' || pages FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id)
        == "fetching/1"
    )


def test_the_orchestrator_refuses_a_gap_and_out_of_order_pages(engine):
    for offset, pages in (
        (36, (SourcePage(0, ()), SourcePage(5, (), is_last=True))),
        (37, (SourcePage(1, (), is_last=True),)),  # the second page arrived first
    ):
        day = DAY + timedelta(offset)
        account = account_id()
        rig = Rig(engine, {account: []})
        rig.adapter.fetch = lambda stream, window, p=pages: iter(p)
        run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
        result = rig.orchestrator.execute(run_id)
        assert (result.status, result.reason) == ("retry", "missing_page")
        assert records(engine, rig.streams[account]) == 0


def test_replayed_pages_must_match_exactly(engine):
    day = DAY + timedelta(38)
    rig, run_id, sid = prepared(engine, day)
    first, second = line(1, day=day), line(2, day=day, svc="S3")
    stage(rig, run_id, sid, SourcePage(0, (first, second)))
    stage(rig, run_id, sid, SourcePage(1, (line(3, day=day, svc="EBS"),)))
    stage(rig, run_id, sid, SourcePage(0, (first, second)))  # identical: harmless
    with pytest.raises(StagingConflict):  # a line it never had
        stage(rig, run_id, sid, SourcePage(0, (first, second, line(4, day=day, svc="New"))))
    with pytest.raises(StagingConflict):  # a line it used to have is gone
        stage(rig, run_id, sid, SourcePage(0, (first,)))
    with pytest.raises(StagingConflict):  # a different value
        stage(rig, run_id, sid, SourcePage(0, (line(9, day=day), second)))
    with pytest.raises(StagingConflict):  # an earlier page cannot end the stream
        stage(rig, run_id, sid, SourcePage(0, (first, second), is_last=True))
    assert staged(engine, run_id) == 3
    assert q(engine, "SELECT status FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id) == "fetching"


def test_no_page_is_accepted_after_the_final_one(engine):
    from app.services.cost_ledger import LedgerFenced

    day = DAY + timedelta(39)
    rig, run_id, sid = prepared(engine, day)
    stage(rig, run_id, sid, SourcePage(0, (line(1, day=day),), is_last=True))
    with pytest.raises(LedgerFenced):
        stage(rig, run_id, sid, SourcePage(1, (line(2, day=day, svc="S3"),)))
    assert staged(engine, run_id) == 1


def test_durable_progress_must_agree_with_the_final_marker(engine, monkeypatch):
    day, account = DAY + timedelta(40), account_id()
    rig = Rig(engine, {account: [[line(1, day=day, bucket="durable")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
    original = ShadowSyncOrchestrator._publish

    def tamper(self, *args, **kwargs):
        with engine.begin() as c:  # a row lost between staging and publication
            c.execute(text("DELETE FROM cost_sync_staging WHERE sync_run_id = :r"), {"r": run_id})
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ShadowSyncOrchestrator, "_publish", tamper)
    result = rig.orchestrator.execute(run_id)
    assert result.status == "failed"
    assert records(engine, rig.streams[account]) == 0
    assert (
        q(engine, "SELECT error_code FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id)
        == "stream_not_complete"
    )


def test_one_run_cannot_publish_a_stream_twice_across_attempts(engine):
    day, account = DAY + timedelta(41), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id, _ = rig.run(window_of(day))
    with pytest.raises(IntegrityError, match="uq_cost_sync_run_streams_published"):
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO cost_sync_run_streams (sync_run_id, connection_id, attempt, team_id, stream_id, window_start, "
                    "window_end, status) VALUES (:r, :c, 2, :t, :s, :a, :b, 'published')"
                ),
                {"r": run_id, "c": rig.conn, "t": A, "s": rig.streams[account], "a": day, "b": day + timedelta(1)},
            )


def test_a_reaper_and_a_worker_racing_on_one_run_leave_one_attempt_in_charge(engine):
    from app.services.ledger_shadow.recovery import reap_abandoned_runs

    day, account = DAY + timedelta(42), account_id()
    rig = Rig(engine, {account: [[line(5, day=day, bucket="race2")], WorkerCrash()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window_of(day))
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    rig.expire()
    rig.adapter.scripts = {account: [[line(5, day=day, bucket="race2")]]}
    results, errors = {}, []
    barrier = threading.Barrier(2)

    def reap():
        barrier.wait(10)
        try:
            with rig.sessions() as s, s.begin():
                reap_abandoned_runs(s)
        except Exception as err:
            errors.append(err)

    def work():
        barrier.wait(10)
        results["worker"] = rig.orchestrator.execute(run_id)

    threads = [threading.Thread(target=reap), threading.Thread(target=work)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert results["worker"].status == "published"
    assert rig.run_state(run_id) == "published/success/2"
    assert money(total(engine, A, day, "race2")) == (Decimal("5.00"), "complete")


# Enrollment


def member(engine, team, role):
    user = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO users (id, email, hashed_password) VALUES (:u, :e, 'x')"),
            {"u": user, "e": f"{user.hex}@t.test"},
        )
        c.execute(
            text("INSERT INTO team_members (id, team_id, user_id, role) VALUES (gen_random_uuid(), :t, :u, :r)"),
            {"t": team, "u": user, "r": role},
        )
    return user


def bare_connection(engine, team, status="active"):
    connection = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO integration_connections (id, team_id, provider, name, config_encrypted, status) "
                "VALUES (:i, :t, 'aws', :n, 'x', :st)"
            ),
            {"i": connection, "t": team, "n": connection.hex[:8], "st": status},
        )
    return connection


def enroll(engine, team, connection, actor, specs, verdicts=None, reason="onboarding"):
    verdicts = verdicts if verdicts is not None else {s.usage_account: VERIFIED for s in specs}
    with Session(engine) as s, s.begin():
        return enroll_connection(
            s,
            team_id=team,
            connection_id=connection,
            actor_user_id=actor,
            specs=specs,
            verdicts=verdicts,
            reason=reason,
        )


def bindings(engine, connection):
    return q(
        engine,
        "SELECT count(*) FROM cost_source_stream_bindings WHERE connection_id = :c AND unbound_at IS NULL",
        c=connection,
    )


def test_enrollment_binds_verified_inventory_and_audits_it(engine):
    team = new_team(engine)
    admin = member(engine, team, "admin")
    connection = bare_connection(engine, team)
    account = account_id()
    enroll(engine, team, connection, admin, [spec(account)])
    assert bindings(engine, connection) == 1
    assert q(engine, "SELECT action FROM audit_logs WHERE team_id = :t", t=team) == "cost_ledger.inventory_enrolled"
    assert q(engine, "SELECT metadata FROM audit_logs WHERE team_id = :t", t=team)["accounts"] == [account]
    assert revoke_with(engine, team, connection, admin) == 1
    assert bindings(engine, connection) == 0
    assert (
        q(
            engine,
            "SELECT count(*) FROM audit_logs WHERE team_id = :t AND action = 'cost_ledger.inventory_revoked'",
            t=team,
        )
        == 1
    )


def revoke_with(engine, team, connection, actor, reason="decommissioned"):
    with Session(engine) as s, s.begin():
        return revoke_connection(s, team_id=team, connection_id=connection, actor_user_id=actor, reason=reason)


def test_enrollment_refusals_leave_nothing_behind(engine):
    team = new_team(engine)
    admin = member(engine, team, "owner")
    viewer = member(engine, team, "viewer")
    connection = bare_connection(engine, team)
    account = account_id()
    specs = [spec(account)]
    cases = [
        (lambda: enroll(engine, team, connection, viewer, specs), "actor_not_authorized"),
        (lambda: enroll(engine, team, connection, uuid.uuid4(), specs), "actor_not_authorized"),
        (lambda: enroll(engine, team, connection, admin, specs, reason="  "), "reason_required"),
        (lambda: enroll(engine, team, connection, admin, []), "inventory_empty"),
        (lambda: enroll(engine, team, connection, admin, specs, {}), "scope_unverified"),
        (
            lambda: enroll(engine, team, connection, admin, specs, {account: ScopeVerdict(False, "payer_mismatch")}),
            "scope_unverified",
        ),
        (lambda: enroll(engine, team, bare_connection(engine, team, "disabled"), admin, specs), "connection_disabled"),
        (lambda: enroll(engine, new_team(engine), connection, admin, specs), "actor_not_authorized"),
    ]
    for call, code in cases:
        with pytest.raises(EnrollmentRefused) as err:
            call()
        assert err.value.code == code
    assert bindings(engine, connection) == 0
    assert q(engine, "SELECT count(*) FROM audit_logs WHERE team_id = :t", t=team) == 0
    assert q(engine, "SELECT count(*) FROM cost_source_streams WHERE usage_account = :a", a=account) == 0


def test_enrollment_needs_shadow_mode_and_never_enrolls_a_team(engine):
    team = new_team(engine, mode=None)
    admin = member(engine, team, "admin")
    with pytest.raises(EnrollmentRefused) as err:
        enroll(engine, team, bare_connection(engine, team), admin, [spec(account_id())])
    assert err.value.code == "team_not_in_shadow_mode"
    assert q(engine, "SELECT count(*) FROM team_cost_ledger_settings WHERE team_id = :t", t=team) == 0


def test_enrollment_refuses_a_duplicate_authority_and_rolls_back(engine):
    team = new_team(engine)
    admin = member(engine, team, "admin")
    account = account_id()
    first = bare_connection(engine, team)
    enroll(engine, team, first, admin, [spec(account, ba="aws:payer:1")])
    second = bare_connection(engine, team)
    with pytest.raises(EnrollmentRefused) as err:
        enroll(engine, team, second, admin, [spec(account, ba="aws:payer:2")])
    assert err.value.code == "source_identity_ambiguous"
    assert bindings(engine, second) == 0
    assert q(engine, "SELECT count(*) FROM cost_source_streams WHERE usage_account = :a", a=account) == 1


def test_enrollment_is_refused_during_a_run_and_revocation_stops_the_next_attempt(engine):
    team = new_team(engine)
    admin = member(engine, team, "admin")
    day, account = DAY + timedelta(43), account_id()
    connection = bare_connection(engine, team)
    enroll(engine, team, connection, admin, [spec(account)])
    rig = Rig(engine, {account: [[line(1, day=day)]]}, team=team, connection=connection)
    run_id = rig.orchestrator.create_run(team, connection, window_of(day))
    with pytest.raises(EnrollmentRefused) as err:
        enroll(engine, team, connection, admin, [spec(account), spec(account_id())])
    assert err.value.code == "run_in_flight"
    with pytest.raises(EnrollmentRefused) as err:
        revoke_with(engine, team, bare_connection(engine, new_team(engine)), admin)
    assert err.value.code == "connection_not_owned"
    assert revoke_with(engine, team, connection, admin) == 1
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("failed", "inventory_drift")
    assert rig.adapter.calls == 0
