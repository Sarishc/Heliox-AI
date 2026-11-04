"""
Regressions for the Step 6F source-level review, on real PostgreSQL with fake provider clients.

Each case asserts the database row itself: a day nothing proves has no coverage and no stream day, and an estimated
day says so. Azure cases use HTTPX mock transports only.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_ledger_shadow_corrections_postgres import (  # noqa: F401
    LINKED,
    PAYER,
    Aws,
    aws_adapter,
    completeness,
    engine,
    gcp_adapter,
    new_team,
    window_of,
)
from test_ledger_shadow_orchestration_postgres import (
    A,
    GcpClient,
    Rig,
    account_id,
    gcp_rows,
    line,
    metrics,
    money,
    q,
    records,
    rig_with,
    spec,
    total,
)

from app.integrations.ledger.azure import AzureCostManagementAdapter, canonical_continuation, is_trusted_continuation
from app.integrations.ledger.base import DAY_ESTIMATED, DAY_FINAL, DAY_UNPROVEN, FetchIncomplete, SourcePage
from app.services.cost_ledger import CostLedgerService, Publication
from app.services.ledger_shadow.coverage import IncompleteInventory, inventory_total, require_complete_total

TODAY = date(2026, 10, 1)
SUB_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SUB_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
QUERY = "/providers/Microsoft.CostManagement/query"
HOST = "https://management.azure.com"
GCP_OK = {"billingAccountName": "billingAccounts/0A1B2C-3D4E5F-6A7B8C", "billingEnabled": True}
COLUMNS = [{"name": n} for n in ("Cost", "CostUSD", "UsageDate", "ServiceName", "ChargeType", "Currency")]
VERSION = "api-version=2026-06-01"


def coverage_row(engine, team, account):
    return q(
        engine, "SELECT state FROM cost_source_coverage WHERE team_id = :t AND usage_account = :a", t=team, a=account
    )


def stream_day_count(engine, sid):
    return q(engine, "SELECT count(*) FROM cost_source_stream_days WHERE stream_id = :s", s=sid)


def assert_unknown(engine, team, day, sid, account):
    assert coverage_row(engine, team, account) is None
    assert stream_day_count(engine, sid) == 0
    assert completeness(engine, team, day, account) == []


# Azure continuation links


SCOPE = f"/subscriptions/{SUB_A}"
GOOD = f"{HOST}{SCOPE}{QUERY}?{VERSION}&$skiptoken=abc"
MALICIOUS = [
    f"{HOST}{SCOPE}{QUERY}/../../../{SUB_B}{QUERY}?{VERSION}",  # the reproduced scope escape
    f"{HOST}{SCOPE}{QUERY}/../../../../subscriptions/{SUB_B}{QUERY}?{VERSION}",
    f"{HOST}/subscriptions/{SUB_B}/../{SUB_A}{QUERY}?{VERSION}",
    f"{HOST}{SCOPE}/./providers/Microsoft.CostManagement/query?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}/%2e%2e/%2e%2e/%2e%2e/{SUB_B}{QUERY}?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}/%2E%2E%2F%2E%2E/x?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}/..%2f..%2fx?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}/%252e%252e/x?{VERSION}",  # double encoded
    f"{HOST}{SCOPE}{QUERY}\\..\\x?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}/?{VERSION}",  # trailing slash
    f"{HOST}{SCOPE}{QUERY}/extra?{VERSION}",  # confusing prefixes
    f"{HOST}{SCOPE}{QUERY}Evil?{VERSION}",
    f"{HOST}{SCOPE}x{QUERY}?{VERSION}",
    f"{HOST}//{SCOPE}{QUERY}?{VERSION}",
    f"{HOST}/subscriptions/{SUB_B}{QUERY}?{VERSION}",  # another scope entirely
    f"https://user:pw@management.azure.com{SCOPE}{QUERY}?{VERSION}",  # credentials in the authority
    f"https://user@management.azure.com{SCOPE}{QUERY}?{VERSION}",
    f"https://management.azure.com@evil.example.com{SCOPE}{QUERY}?{VERSION}",
    f"https://evil.example.com{SCOPE}{QUERY}?{VERSION}",
    f"https://management.azure.com.evil.example{SCOPE}{QUERY}?{VERSION}",
    f"http://management.azure.com{SCOPE}{QUERY}?{VERSION}",
    f"https://management.azure.com:8443{SCOPE}{QUERY}?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}#frag",  # a fragment
    f"{HOST}{SCOPE}{QUERY}",  # unexpected query structure
    f"{HOST}{SCOPE}{QUERY}?$skiptoken=abc",
    f"{HOST}{SCOPE}{QUERY}?api-version=2020-01-01",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}&{VERSION}",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}&$skiptoken=a&$skiptoken=b",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}&redirect=https://evil.example.com",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}&novalue",
    f"{HOST}{SCOPE}{QUERY};x=1?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}\t",
    f" {HOST}{SCOPE}{QUERY}?{VERSION}",
    f"{HOST}{SCOPE}{QUERY}?{VERSION}&$skiptoken=é",
    12345,
]


@pytest.mark.parametrize("evil", MALICIOUS, ids=[str(i) for i in range(len(MALICIOUS))])
def test_azure_malicious_continuation_never_receives_the_token(evil):
    assert canonical_continuation(evil, SCOPE) is None
    sent = []

    def handler(request):
        sent.append(request)
        if len(sent) == 1:
            return httpx.Response(200, json={"properties": {"columns": COLUMNS, "rows": [], "nextLink": evil}})
        raise AssertionError(f"a request reached {request.url}")

    adapter = AzureCostManagementAdapter(
        {"subscription_ids": [SUB_A]},
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda force: "secret-bearer",
        sleep=lambda s: None,
    )
    with pytest.raises(FetchIncomplete) as err:
        list(adapter.fetch(adapter.streams()[0], window_of(date(2026, 1, 1))))
    assert err.value.code == "untrusted_continuation_url"
    assert len(sent) == 1  # only the adapter's own first request ever carried the token
    assert sent[0].url.path == f"{SCOPE}{QUERY}"


@pytest.mark.parametrize(
    "evil",
    [
        f"{HOST}/providers/Microsoft.Billing/billingAccounts/BA-1/billingSubscriptions/../../BA-2/billingSubscriptions?api-version=2024-04-01",
        f"{HOST}/providers/Microsoft.Billing/billingAccounts/BA-1/billingSubscriptions/%2e%2e/x?api-version=2024-04-01",
        f"{HOST}/providers/Microsoft.Billing/billingAccounts/BA-2/billingSubscriptions?api-version=2024-04-01",
        f"{HOST}/providers/Microsoft.Billing/billingAccounts/BA-1/billingSubscriptions?api-version=2026-06-01",
        "https://evil.example.com/providers/Microsoft.Billing/billingAccounts/BA-1/billingSubscriptions?api-version=2024-04-01",
    ],
)
def test_azure_billing_list_continuation_is_validated_the_same_way(evil):
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"value": [], "nextLink": evil})

    adapter = AzureCostManagementAdapter(
        {"subscription_ids": [SUB_A], "billing_account_id": "BA-1", "use_billing_account_scope": True},
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda force: "secret-bearer",
        sleep=lambda s: None,
    )
    verdict = adapter.verify_scope()[f"azure:sub:{SUB_A}"]
    assert (verdict.verified, verdict.code) == (False, "untrusted_continuation_url")
    assert len(sent) == 1


@pytest.mark.parametrize(
    "url,scope,resource,version",
    [
        (GOOD, SCOPE, QUERY, "2026-06-01"),
        (f"{HOST}:443{SCOPE}{QUERY}?{VERSION}&$skiptoken=abc", SCOPE, QUERY, "2026-06-01"),
        (f"{HOST}{SCOPE.upper()}{QUERY.lower()}?{VERSION}&%24skiptoken=a%2Bb%3D", SCOPE, QUERY, "2026-06-01"),
        (f"{HOST}{SCOPE}{QUERY}?$skiptoken=abc&{VERSION}", SCOPE, QUERY, "2026-06-01"),
        (
            f"{HOST}/providers/Microsoft.Billing/billingAccounts/BA-1/billingSubscriptions?api-version=2024-04-01&$top=50&$skip=50",
            "/providers/Microsoft.Billing/billingAccounts/BA-1",
            "/billingSubscriptions",
            "2024-04-01",
        ),
        (
            f"{HOST}/providers/Microsoft.Billing/billingAccounts/a%3Ab/billingSubscriptions?api-version=2024-04-01",
            "/providers/Microsoft.Billing/billingAccounts/a:b",
            "/billingSubscriptions",
            "2024-04-01",
        ),
    ],
)
def test_azure_legitimate_pagination_links_are_accepted(url, scope, resource, version):
    assert is_trusted_continuation(url, scope, resource, version)


def test_azure_sends_exactly_the_url_it_validated():
    sent = []

    def handler(request):
        sent.append(request)
        properties = {"columns": COLUMNS, "rows": []}
        if len(sent) == 1:
            properties["nextLink"] = GOOD
        return httpx.Response(200, json={"properties": properties})

    adapter = AzureCostManagementAdapter(
        {"subscription_ids": [SUB_A]},
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda force: "secret-bearer",
        sleep=lambda s: None,
    )
    assert list(adapter.fetch(adapter.streams()[0], window_of(date(2026, 1, 1))))[-1].is_last
    assert str(sent[1].url) == canonical_continuation(GOOD, SCOPE) == GOOD
    assert sent[1].headers["Authorization"] == "Bearer secret-bearer"


# Empty days: AWS


class EstimatedAws(Aws):
    def get_cost_and_usage(self, **kwargs):
        response = super().get_cost_and_usage(**kwargs)
        response["ResultsByTime"][0]["Estimated"] = True
        return response


class LateJoiner(Aws):
    """The linked account joined this organization after the requested window."""

    def __init__(self, day, joined, amount=None):
        super().__init__(day, amount=amount)
        self.joined = joined

    def list_accounts(self, **kwargs):
        account = {"Id": LINKED, "State": "ACTIVE"}
        if self.joined:
            account["JoinedTimestamp"] = self.joined
        return {"Accounts": [account]}


def test_aws_estimated_empty_day_is_not_a_final_zero(engine):
    """Before: coverage 'final', financial 'complete'. After: both say estimated."""
    team, day = new_team(engine), date(2026, 2, 3)
    account = f"aws:acct:{LINKED}"
    rig = rig_with(engine, aws_adapter([LINKED], EstimatedAws(day)), team)
    _, result = rig.run(window_of(day))
    assert result.status == "published"
    assert coverage_row(engine, team, account) == "estimated"
    assert (
        q(
            engine,
            "SELECT state || '/' || record_count FROM cost_source_stream_days WHERE stream_id = :s",
            s=rig.streams[account],
        )
        == "estimated/0"
    )
    [c] = completeness(engine, team, day, account)
    assert (c.fetch_state, c.financial_state) == ("estimated", "estimated")
    with Session(engine) as s:
        report = inventory_total(s, team, "aws", day)
    assert (report.state, report.confirmed_usd) == ("estimated", None)


def test_aws_proven_zero_day_still_works(engine):
    team, day = new_team(engine), date(2026, 2, 4)
    account = f"aws:acct:{LINKED}"
    rig = rig_with(engine, aws_adapter([LINKED], Aws(day)), team)
    _, result = rig.run(window_of(day))
    assert result.status == "published"
    assert coverage_row(engine, team, account) == "final"
    [c] = completeness(engine, team, day, account)
    assert (c.financial_state, c.converted_total_usd) == ("complete", Decimal("0"))


@pytest.mark.parametrize(
    "joined", [datetime(2026, 6, 1, tzinfo=timezone.utc), None], ids=["joined_later", "join_date_unknown"]
)
def test_aws_days_before_an_account_joined_cannot_be_zero(engine, joined):
    team, day = new_team(engine), date(2026, 2, 5)
    account = f"aws:acct:{LINKED}"
    rig = rig_with(engine, aws_adapter([LINKED], LateJoiner(day, joined)), team)
    run_id, result = rig.run(window_of(day))
    assert result.status == "partial"
    assert_unknown(engine, team, day, rig.streams[account], account)
    assert metrics(engine, run_id)["ledger"]["inventory"]["unproven_days"] == {account: [day.isoformat()]}


def test_aws_days_after_joining_are_proven_and_rows_before_it_still_count(engine):
    team, day = new_team(engine), date(2026, 2, 6)
    account = f"aws:acct:{LINKED}"
    after = rig_with(engine, aws_adapter([LINKED], LateJoiner(day, datetime(2026, 1, 1, tzinfo=timezone.utc))), team)
    assert after.run(window_of(day))[1].status == "published"
    assert coverage_row(engine, team, account) == "final"
    team2 = new_team(engine)
    costly = rig_with(
        engine, aws_adapter([LINKED], LateJoiner(day, datetime(2026, 6, 1, tzinfo=timezone.utc), amount="40")), team2
    )
    assert costly.run(window_of(day))[1].status == "published"  # rows are evidence, whatever the join date says
    assert money(total(engine, team2, day, "ec2")) == (Decimal("40.00"), "complete")


def test_aws_estimated_flag_on_any_page_of_a_day_holds():
    from app.integrations.ledger.aws import AwsCostExplorerAdapter

    day = date(2026, 2, 7)

    def period(estimated):
        return {
            "TimePeriod": {"Start": day.isoformat(), "End": (day + timedelta(1)).isoformat()},
            "Groups": [],
            "Total": {},
            "Estimated": estimated,
        }

    class Client(Aws):
        def get_cost_and_usage(self, **kwargs):
            if kwargs.get("NextPageToken"):
                return {"ResultsByTime": [period(False)]}
            return {"ResultsByTime": [period(True)], "NextPageToken": "p2"}

    adapter = AwsCostExplorerAdapter(
        {"payer_account_id": PAYER, "linked_account_ids": [LINKED]}, client_factory=Client(day)
    )
    adapter.verify_scope()
    pages = list(adapter.fetch(adapter.streams()[0], window_of(day)))
    assert pages[-1].day_evidence == {day: DAY_ESTIMATED}


# Empty days: Azure


def azure_adapter(rows=(), config=None):
    def handler(request):
        url = str(request.url)
        if request.method == "GET" and "billingSubscriptions" in url:
            return httpx.Response(200, json={"value": [{"properties": {"subscriptionId": SUB_A}}]})
        if request.method == "GET":
            return httpx.Response(200, json={"state": "Enabled"})
        body = request.read().decode()
        if '"name":"SubscriptionId"}]' in body.replace(" ", ""):
            return httpx.Response(
                200, json={"properties": {"columns": [{"name": "SubscriptionId"}], "rows": [[SUB_A]]}}
            )
        return httpx.Response(200, json={"properties": {"columns": COLUMNS, "rows": list(rows)}})

    return AzureCostManagementAdapter(
        {"subscription_ids": [SUB_A], **(config or {})},
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda force: "t",
        sleep=lambda s: None,
        today=lambda: TODAY,
    )


BILLING_SCOPE = {"billing_account_id": "BA-1", "use_billing_account_scope": True}
AZURE_ACCOUNT = f"azure:sub:{SUB_A}"


def test_azure_recent_day_with_no_rows_is_estimated_not_final(engine):
    team, recent = new_team(engine), date(2026, 9, 30)
    rig = rig_with(engine, azure_adapter(), team)
    assert rig.run(window_of(recent))[1].status == "published"
    assert coverage_row(engine, team, AZURE_ACCOUNT) == "estimated"
    [c] = completeness(engine, team, recent, AZURE_ACCOUNT)
    assert (c.fetch_state, c.financial_state) == ("estimated", "estimated")


def test_azure_settled_subscription_day_with_no_rows_is_a_proven_zero(engine):
    team, old = new_team(engine), date(2026, 8, 1)
    rig = rig_with(engine, azure_adapter(), team)
    assert rig.run(window_of(old))[1].status == "published"
    assert coverage_row(engine, team, AZURE_ACCOUNT) == "final"
    [c] = completeness(engine, team, old, AZURE_ACCOUNT)
    assert (c.financial_state, c.converted_total_usd) == ("complete", Decimal("0"))


def test_azure_billing_scope_empty_day_is_unknown_because_billing_can_move(engine):
    team, old = new_team(engine), date(2026, 8, 2)
    rig = rig_with(engine, azure_adapter(config=BILLING_SCOPE), team)
    run_id, result = rig.run(window_of(old))
    assert result.status == "partial"
    assert_unknown(engine, team, old, rig.streams[AZURE_ACCOUNT], AZURE_ACCOUNT)
    assert metrics(engine, run_id)["ledger"]["inventory"]["unproven_days"] == {AZURE_ACCOUNT: [old.isoformat()]}


def test_azure_billing_scope_day_with_rows_is_known(engine):
    team, old = new_team(engine), date(2026, 8, 3)
    rows = [[54, 54, int(old.strftime("%Y%m%d")), "Virtual Machines", "Usage", "USD"]]
    rig = rig_with(engine, azure_adapter(rows, BILLING_SCOPE), team)
    assert rig.run(window_of(old))[1].status == "published"
    assert money(total(engine, team, old, "azure_vm", "azure")) == (Decimal("54.00"), "complete")


# Empty days and history: GCP


def gcp(rows, lookup=None):
    return gcp_adapter(["ml-prod-1"], lookup or (lambda p: GCP_OK), GcpClient(rows))


GCP_ACCOUNT = "gcp:project:ml-prod-1"


def test_gcp_project_that_moved_accounts_is_unknown_for_earlier_days(engine):
    """Before: 'final', 'complete', $0. Current association and other rows' export_time prove nothing about then."""
    team, day = new_team(engine), date(2026, 1, 15)
    rig = rig_with(engine, gcp([]), team)
    run_id, result = rig.run(window_of(day))
    assert result.status == "partial"
    assert_unknown(engine, team, day, rig.streams[GCP_ACCOUNT], GCP_ACCOUNT)
    assert metrics(engine, run_id)["ledger"]["inventory"]["unproven_days"][GCP_ACCOUNT] == [day.isoformat()]
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts WHERE team_id = :t", t=team) == 0


def test_gcp_recent_empty_window_is_unknown(engine):
    team, recent = new_team(engine), date(2026, 9, 30)
    rig = rig_with(engine, gcp([]), team)
    assert rig.run(window_of(recent))[1].status == "partial"
    assert_unknown(engine, team, recent, rig.streams[GCP_ACCOUNT], GCP_ACCOUNT)


def test_gcp_rows_that_sum_to_zero_are_a_proven_zero(engine):
    team, day = new_team(engine), date(2026, 7, 10)
    rig = rig_with(engine, gcp(gcp_rows(day, "10", "-10")), team)
    rig.run(window_of(day))
    assert coverage_row(engine, team, GCP_ACCOUNT) == "final"
    [c] = completeness(engine, team, day, GCP_ACCOUNT)
    assert (c.financial_state, c.converted_total_usd) == ("complete", Decimal("0"))


def test_gcp_a_window_is_decided_day_by_day(engine):
    team, first = new_team(engine), date(2026, 7, 11)
    second = first + timedelta(1)
    rig = rig_with(engine, gcp(gcp_rows(first, "10")), team)
    run_id, _ = rig.run(window_of(first, 2))
    assert (
        q(
            engine,
            "SELECT string_agg(usage_date::text, ',') FROM cost_source_stream_days WHERE stream_id = :s",
            s=rig.streams[GCP_ACCOUNT],
        )
        == first.isoformat()
    )
    assert metrics(engine, run_id)["ledger"]["inventory"]["unproven_days"][GCP_ACCOUNT] == [second.isoformat()]


def test_gcp_day_is_estimated_until_its_invoice_month_should_have_closed(engine):
    """Before: a day in a month closed yesterday read as 'final'."""
    team, day = new_team(engine), date(2026, 9, 10)
    rig = rig_with(engine, gcp(gcp_rows(day, "100")), team)
    rig.run(window_of(day))
    assert coverage_row(engine, team, GCP_ACCOUNT) == "estimated"
    [c] = completeness(engine, team, day, GCP_ACCOUNT)
    assert c.financial_state == "estimated"
    closed = new_team(engine)
    settled = date(2026, 8, 10)
    later = rig_with(engine, gcp(gcp_rows(settled, "100")), closed)
    later.run(window_of(settled))
    assert coverage_row(engine, closed, GCP_ACCOUNT) == "final"


def test_gcp_late_correction_after_a_caught_up_export_is_applied_with_its_trail(engine):
    team, day = new_team(engine), date(2026, 7, 20)
    rig = rig_with(engine, gcp(gcp_rows(day, "100")), team)
    rig.run(window_of(day))
    assert coverage_row(engine, team, GCP_ACCOUNT) == "final"
    assert money(total(engine, team, day, "gcp-compute", "gcp")) == (Decimal("100.00"), "complete")
    # The export's watermark had already passed this day when the correction arrived
    rig.adapter._client_factory = GcpClient(gcp_rows(day, "130"))
    rig.run(window_of(day))
    assert money(total(engine, team, day, "gcp-compute", "gcp")) == (Decimal("130.00"), "complete")
    assert (
        q(
            engine,
            "SELECT string_agg(o.change_kind, ',' ORDER BY o.generation) FROM cost_source_observations o "
            "JOIN cost_source_records r ON r.id = o.record_id WHERE r.stream_id = :s",
            s=rig.streams[GCP_ACCOUNT],
        )
        == "inserted,corrected"
    )
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts WHERE team_id = :t", t=team) == 1


def test_gcp_rows_that_vanish_are_held_not_retired_or_zeroed(engine):
    team, day = new_team(engine), date(2026, 7, 21)
    rig = rig_with(engine, gcp(gcp_rows(day, "100")), team)
    rig.run(window_of(day))
    rig.adapter._client_factory = GcpClient([])
    rig.run(window_of(day))
    assert coverage_row(engine, team, GCP_ACCOUNT) == "suspect_empty"
    assert money(total(engine, team, day, "gcp-compute", "gcp")) == (Decimal("100.00"), "incomplete")
    assert (
        q(
            engine,
            "SELECT count(*) FROM cost_source_records WHERE stream_id = :s AND state = 'absent'",
            s=rig.streams[GCP_ACCOUNT],
        )
        == 0
    )


# The evidence contract itself


def test_a_last_page_without_evidence_proves_nothing(engine):
    day, account = date(2026, 2, 10), account_id()
    rig = Rig(engine, {account: []})
    rig.adapter.fetch = lambda stream, window: iter([SourcePage(0, (), is_last=True)])
    run_id, result = rig.run(window_of(day))
    assert result.status == "partial"
    assert_unknown(engine, A, day, rig.streams[account], account)
    assert account in metrics(engine, run_id)["ledger"]["inventory"]["unproven_days"]


def test_evidence_is_per_day_and_lines_outrank_unproven(engine):
    first, account = date(2026, 2, 11), account_id()
    second, third = first + timedelta(1), first + timedelta(2)
    rig = Rig(
        engine,
        {account: [[line(5, day=first, bucket="evid")]]},
        evidence={first: DAY_UNPROVEN, second: DAY_ESTIMATED, third: DAY_FINAL},
    )
    rig.run(window_of(first, 3))
    with engine.connect() as c:
        rows = dict(
            c.execute(
                text("SELECT usage_date, state FROM cost_source_stream_days WHERE stream_id = :s"),
                {"s": rig.streams[account]},
            )
            .tuples()
            .all()
        )
    assert rows == {first: "final", second: "estimated", third: "final"}


def test_step_6e_publication_without_evidence_keeps_its_meaning(engine):
    """The service's defaults are unchanged: only a caller that states evidence gets the new behaviour."""
    day, account = date(2026, 2, 15), account_id()
    rig = Rig(engine, {account: [[]]})
    with rig.sessions() as s, s.begin():
        service = CostLedgerService(s)
        run = service.start_run(rig.conn)
        token = service.acquire_lease(run)
        out = service.publish(Publication(run, 1, token, rig.streams[account], day, day + timedelta(1), [], True))
        service.finish_run(run, attempt=1, fencing_token=token)
    assert (out.published_days, out.unproven_days) == ([day], [])
    assert coverage_row(engine, A, account) == "final"


# Partial inventory


def inventory(engine, team, provider, day):
    with Session(engine) as s:
        return inventory_total(s, team, provider, day)


def test_100_of_a_two_account_inventory_is_never_the_total(engine):
    team, day = new_team(engine), date(2026, 2, 20)
    known, missing = account_id(), account_id()
    rig = Rig(
        engine,
        {known: [[line(100, day=day, bucket="partial")]], missing: [FetchIncomplete("access_denied")]},
        team=team,
    )
    _, result = rig.run(window_of(day))
    assert result.status == "partial"
    # The bucket subtotal says what it is
    bucket = total(engine, team, day, "partial")
    assert (bucket.amount_usd, bucket.scope) == (Decimal("100.00"), "known_contributions")
    # The inventory-aware total refuses to call it complete
    report = inventory(engine, team, "aws", day)
    assert (report.state, report.scope) == ("incomplete", "known_contributions")
    assert (report.known_usd, report.confirmed_usd) == (Decimal("100.00"), None)
    assert (report.complete, report.unknown) == ((known,), (missing,))
    assert set(report.expected) == {known, missing}
    with Session(engine) as s, pytest.raises(IncompleteInventory) as err:
        require_complete_total(s, team, "aws", day)
    assert err.value.total.unknown == (missing,)
    # Once the missing account is proven, the total is real
    rig.adapter.scripts = {
        known: [[line(100, day=day, bucket="partial")]],
        missing: [[line(50, day=day, bucket="partial")]],
    }
    assert rig.run(window_of(day))[1].status == "published"
    report = inventory(engine, team, "aws", day)
    assert (report.state, report.scope, report.confirmed_usd) == (
        "complete",
        "all_expected_accounts",
        Decimal("150.00"),
    )
    with Session(engine) as s:
        assert require_complete_total(s, team, "aws", day) == Decimal("150.00")


def test_inventory_total_estimated_unconverted_conflict_and_empty_inventory(engine):
    team = new_team(engine)
    day = date(2026, 2, 21)
    assert inventory(engine, team, "aws", day).state == "incomplete"  # nothing expected is not a total of zero
    account = account_id()
    rig = Rig(engine, {account: [[line(10, day=day, est=True)]]}, team=team)
    rig.run(window_of(day))
    report = inventory(engine, team, "aws", day)
    assert (report.state, report.confirmed_usd, report.estimated) == ("estimated", None, (account,))
    rig.run(window_of(day), {account: [[line(10, day=day, cur="EUR")]]})
    report = inventory(engine, team, "aws", day)
    assert (report.state, report.confirmed_usd, report.incomplete) == ("incomplete", None, (account,))
    rig.run(window_of(day), {account: [[line(10, day=day)]]})
    witness = Rig(engine, {account: [[line(9, day=day)]]}, team=team, specs=[spec(account, vantage="aws:caller:w")])
    witness.run(window_of(day))
    report = inventory(engine, team, "aws", day)
    assert (report.state, report.confirmed_usd) == ("incomplete", None)
    assert report.known_usd == Decimal("10.00")  # the witness adds nothing


def test_inventory_total_is_per_tenant_and_per_provider(engine):
    day = date(2026, 2, 22)
    team, other = new_team(engine), new_team(engine)
    mine = account_id()
    Rig(engine, {mine: [[line(10, day=day)]]}, team=team).run(window_of(day))
    theirs = account_id()
    Rig(engine, {theirs: [FetchIncomplete("access_denied")]}, team=other).run(window_of(day))
    assert inventory(engine, team, "aws", day).confirmed_usd == Decimal("10.00")
    assert inventory(engine, other, "aws", day).unknown == (theirs,)
    assert inventory(engine, team, "gcp", day).state == "incomplete"


def test_an_account_no_longer_expected_cannot_complete_a_total(engine):
    day, account = date(2026, 2, 23), account_id()
    team = new_team(engine)
    rig = Rig(engine, {account: [[line(10, day=day)]]}, team=team)
    rig.run(window_of(day))
    assert inventory(engine, team, "aws", day).state == "complete"
    with engine.begin() as c:
        c.execute(
            text("UPDATE cost_source_stream_bindings SET unbound_at = now() WHERE connection_id = :c"), {"c": rig.conn}
        )
    report = inventory(engine, team, "aws", day)
    assert (report.state, report.confirmed_usd, report.known_usd) == ("incomplete", None, Decimal("10.00"))
    assert records(engine, rig.streams[account]) == 1
