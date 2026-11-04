"""
Ledger adapters against fake provider clients: no network, no live credentials, no database.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from app.integrations.ledger.aws import AwsCostExplorerAdapter
from app.integrations.ledger.azure import AzureCostManagementAdapter, is_trusted_continuation
from app.integrations.ledger.base import AdapterConfigError, DateWindow, FetchIncomplete
from app.integrations.ledger.gcp import NO_PROJECT, GcpBillingExportAdapter

DAY = date(2026, 9, 1)
WINDOW = DateWindow(DAY, DAY + timedelta(2))
PAYER = "111111111111"
MEMBER = "222222222222"
SUB_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SUB_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
EXPORT_TABLE = "gcp_billing_export_v1_0A1B2C_3D4E5F_6A7B8C"
BILLING_ACCOUNT = "0A1B2C-3D4E5F-6A7B8C"


def collect(adapter, spec, window=WINDOW):
    return list(adapter.fetch(spec, window))


def lines_of(pages):
    return [ln for page in pages for ln in page.lines]


def incomplete(adapter, spec, code, window=WINDOW):
    with pytest.raises(FetchIncomplete) as err:
        collect(adapter, spec, window)
    assert err.value.code == code
    return err.value


# AWS


def group(service, record, amount, unit="USD"):
    return {"Keys": [service, record], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": unit}}}


def period(day, groups, estimated=False):
    return {
        "TimePeriod": {"Start": day.isoformat(), "End": (day + timedelta(1)).isoformat()},
        "Groups": groups,
        "Total": {},
        "Estimated": estimated,
    }


class FakeAws:
    """Serves scripted Cost Explorer pages keyed by NextPageToken."""

    def __init__(self, pages, caller=PAYER, error=None, dimension_values=()):
        self.pages, self.caller, self.error, self.requests = pages, caller, error, []
        self.dimension_values = dimension_values

    def __call__(self, service):
        return self

    def get_caller_identity(self):
        return {"Account": self.caller}

    def get_cost_and_usage(self, **kwargs):
        self.requests.append(kwargs)
        token = kwargs.get("NextPageToken")
        if self.error and token == self.error[0]:
            raise self.error[1]
        return self.pages[token]

    def get_dimension_values(self, **kwargs):
        return {"DimensionValues": [{"Value": v} for v in self.dimension_values]}


def aws(pages, accounts=(PAYER,), **kwargs):
    fake = FakeAws(pages, **kwargs)
    return (
        AwsCostExplorerAdapter({"payer_account_id": PAYER, "linked_account_ids": list(accounts)}, client_factory=fake),
        fake,
    )


def test_aws_single_page():
    pages = {
        None: {"ResultsByTime": [period(DAY, [group("Amazon EC2", "Usage", "100.5")]), period(DAY + timedelta(1), [])]}
    }
    adapter, fake = aws(pages)
    spec = adapter.streams()[0]
    result = collect(adapter, spec)
    assert [p.is_last for p in result] == [True]
    [line] = lines_of(result)
    assert (line.amount, line.currency, line.charge_class, line.cost_bucket) == (
        Decimal("100.5"),
        "USD",
        "usage",
        "ec2",
    )
    assert (spec.billing_account, spec.usage_account, spec.vantage) == (
        f"aws:payer:{PAYER}",
        f"aws:acct:{PAYER}",
        f"aws:caller:{PAYER}",
    )
    # Half-open window, passed exactly; one account filter; no tag grouping
    request = fake.requests[0]
    assert request["TimePeriod"] == {"Start": "2026-09-01", "End": "2026-09-03"}
    assert request["Filter"]["Dimensions"] == {"Key": "LINKED_ACCOUNT", "Values": [PAYER]}
    assert all(g["Type"] == "DIMENSION" for g in request["GroupBy"])


def test_aws_multiple_pages_are_all_read_before_completion():
    pages = {
        None: {"ResultsByTime": [period(DAY, [group("Amazon EC2", "Usage", "1")])], "NextPageToken": "p2"},
        "p2": {"ResultsByTime": [period(DAY, [group("Amazon S3", "Usage", "2")])], "NextPageToken": "p3"},
        "p3": {"ResultsByTime": [period(DAY + timedelta(1), [group("Amazon S3", "Usage", "3")])]},
    }
    adapter, fake = aws(pages)
    result = collect(adapter, adapter.streams()[0])
    assert [(p.seq, p.is_last) for p in result] == [(0, False), (1, False), (2, True)]
    assert sum(ln.amount for ln in lines_of(result)) == Decimal("6")
    assert [r.get("NextPageToken") for r in fake.requests] == [None, "p2", "p3"]


def test_aws_missing_continuation_page_is_incomplete():
    pages = {None: {"ResultsByTime": [period(DAY, [])], "NextPageToken": "p2"}}
    adapter, _ = aws(pages, error=("p2", RuntimeError("connection reset")))
    spec = adapter.streams()[0]
    seen = []
    with pytest.raises(FetchIncomplete) as err:
        for page in adapter.fetch(spec, WINDOW):
            seen.append(page)
    assert err.value.code == "provider_request_failed" and err.value.retryable
    assert [p.is_last for p in seen] == [False]  # completion is never signalled


def test_aws_repeated_continuation_token_is_incomplete():
    pages = {
        None: {"ResultsByTime": [period(DAY, [])], "NextPageToken": "p2"},
        "p2": {"ResultsByTime": [period(DAY + timedelta(1), [])], "NextPageToken": "p2"},
    }
    adapter, _ = aws(pages)
    assert not incomplete(adapter, adapter.streams()[0], "repeated_page_token").retryable


def test_aws_missing_day_is_incomplete():
    adapter, _ = aws({None: {"ResultsByTime": [period(DAY, [])]}})
    incomplete(adapter, adapter.streams()[0], "missing_days")


def test_aws_linked_accounts_are_separate_streams_with_their_own_query():
    pages = {None: {"ResultsByTime": [period(DAY, []), period(DAY + timedelta(1), [])]}}
    adapter, fake = aws(pages, accounts=(PAYER, MEMBER))
    specs = adapter.streams()
    assert [s.usage_account for s in specs] == [f"aws:acct:{PAYER}", f"aws:acct:{MEMBER}"]
    collect(adapter, specs[1])
    assert fake.requests[0]["Filter"]["Dimensions"]["Values"] == [MEMBER]


def test_aws_member_caller_cannot_claim_other_accounts():
    adapter, _ = aws({None: {"ResultsByTime": []}}, accounts=(PAYER, MEMBER), caller=MEMBER)
    specs = {s.usage_account: s for s in adapter.streams()}
    assert specs[f"aws:acct:{MEMBER}"].vantage == f"aws:caller:{MEMBER}"
    incomplete(adapter, specs[f"aws:acct:{PAYER}"], "account_not_visible_to_caller")
    assert not adapter.discover(WINDOW).supported


def test_aws_negative_zero_and_credit_lines_are_retained():
    groups = [
        group("Amazon EC2", "Usage", "100"),
        group("Amazon EC2", "Credit", "-15.25"),
        group("Amazon S3", "Usage", "0"),
        group("Tax", "Tax", "1.5"),
    ]
    adapter, _ = aws({None: {"ResultsByTime": [period(DAY, groups), period(DAY + timedelta(1), [])]}})
    lines = lines_of(collect(adapter, adapter.streams()[0]))
    assert [(ln.line_kind, ln.charge_class, ln.amount) for ln in lines] == [
        ("aws:Usage", "usage", Decimal("100")),
        ("aws:Credit", "credit", Decimal("-15.25")),
        ("aws:Usage", "usage", Decimal("0")),
        ("aws:Tax", "tax", Decimal("1.5")),
    ]


@pytest.mark.parametrize(
    "bad,code",
    [
        ({"Keys": ["Amazon EC2", "Usage"], "Metrics": {}}, "missing_cost_value"),
        ({"Keys": ["Amazon EC2", "Usage"], "Metrics": {"UnblendedCost": {"Unit": "USD"}}}, "missing_cost_value"),
        (
            {"Keys": ["Amazon EC2", "Usage"], "Metrics": {"UnblendedCost": {"Amount": None, "Unit": "USD"}}},
            "malformed_cost_value",
        ),
        (
            {"Keys": ["Amazon EC2", "Usage"], "Metrics": {"UnblendedCost": {"Amount": "abc", "Unit": "USD"}}},
            "malformed_cost_value",
        ),
        (
            {"Keys": ["Amazon EC2"], "Metrics": {"UnblendedCost": {"Amount": "1", "Unit": "USD"}}},
            "malformed_group_keys",
        ),
    ],
)
def test_aws_missing_or_malformed_cost_never_becomes_a_value(bad, code):
    adapter, _ = aws({None: {"ResultsByTime": [period(DAY, [bad]), period(DAY + timedelta(1), [])]}})
    incomplete(adapter, adapter.streams()[0], code)


def test_aws_estimated_flag_and_foreign_unit_are_preserved():
    groups = [group("Amazon EC2", "Usage", "10", unit="EUR")]
    adapter, _ = aws({None: {"ResultsByTime": [period(DAY, groups, estimated=True), period(DAY + timedelta(1), [])]}})
    [line] = lines_of(collect(adapter, adapter.streams()[0]))
    assert (line.is_estimated, line.currency, line.amount_usd) == (True, "EUR", None)


def test_aws_inventory_must_be_explicit():
    with pytest.raises(AdapterConfigError) as err:
        AwsCostExplorerAdapter({"payer_account_id": PAYER, "linked_account_ids": []}, client_factory=FakeAws({}))
    assert err.value.code == "invalid_linked_accounts"


def test_aws_discovery_reports_accounts_for_a_payer():
    adapter, _ = aws({}, dimension_values=(PAYER, "333333333333"))
    assert adapter.discover(WINDOW).accounts == {f"aws:acct:{PAYER}", "aws:acct:333333333333"}


# GCP


class FakeRows:
    def __init__(self, pages, total=None, fail_at=None):
        self._pages, self.total_rows, self._fail_at = pages, total, fail_at

    @property
    def pages(self):
        for i, page in enumerate(self._pages):
            if self._fail_at == i:
                raise RuntimeError("page fetch failed")
            yield page


class FakeBigQuery:
    def __init__(self, pages, *, export_time=datetime(2026, 9, 10, tzinfo=timezone.utc), total="auto", fail_at=None):
        self.pages, self.export_time, self.fail_at = pages, export_time, fail_at
        self.total = sum(len(p) for p in pages) if total == "auto" else total
        self.queries = []

    def __call__(self):
        return self

    def query(self, sql, job_config=None):
        self.queries.append((sql, job_config))
        return self

    def result(self):
        sql = self.queries[-1][0]
        if sql.startswith("SELECT MAX(export_time)"):
            return FakeRows([[{"last_export": self.export_time}]])
        if "DISTINCT project.id" in sql:
            return FakeRows([[{"project_id": "ml-prod-1"}, {"project_id": "surprise-9"}]])
        return FakeRows(self.pages, self.total, self.fail_at)


def gcp_row(**over):
    row = dict(
        usage_day=DAY,
        service_id="6F81",
        service_name="Compute Engine",
        line_type="cost",
        sub_type="regular",
        currency="USD",
        invoice_month="202609",
        amount=Decimal("100"),
        rate_min=Decimal("1"),
        rate_max=Decimal("1"),
        last_export=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    row.update(over)
    return row


GCP_CONFIG = {
    "gcp_project_id": "billing-admin-1",
    "bigquery_dataset": "billing_export",
    "billing_export_table": EXPORT_TABLE,
    "billing_account_id": BILLING_ACCOUNT,
    "project_ids": ["ml-prod-1", "ml-dev-2"],
}


def gcp(pages=(), config=None, **kwargs):
    fake = FakeBigQuery(list(pages), **kwargs)
    return (
        GcpBillingExportAdapter(
            {**GCP_CONFIG, **(config or {})},
            client_factory=fake,
            parameters=lambda values: list(values),
            today=lambda: date(2026, 9, 30),
        ),
        fake,
    )


def spec_for(adapter, project="ml-prod-1"):
    return next(s for s in adapter.streams() if s.usage_account == f"gcp:project:{project}")


def test_gcp_multiple_result_pages():
    adapter, _ = gcp([[gcp_row()], [gcp_row(service_id="AAAA")], [gcp_row(service_id="BBBB", amount=Decimal("3"))]])
    pages = collect(adapter, spec_for(adapter))
    assert [(p.seq, p.is_last) for p in pages] == [(0, False), (1, False), (2, True)]
    assert sum(ln.amount for ln in lines_of(pages)) == Decimal("203")


def test_gcp_query_includes_credits_and_never_filters_positive_cost_or_reads_labels():
    adapter, fake = gcp([[]])
    collect(adapter, spec_for(adapter))
    sql, params = fake.queries[0]
    assert "cost > 0" not in sql and "labels" not in sql
    assert "UNNEST(credits)" in sql
    assert ("project", "STRING", "ml-prod-1") in params
    assert ("start_date", "DATE", WINDOW.start) in params and ("end_date", "DATE", WINDOW.end) in params
    assert "DATE(usage_start_time) < @end_date" in sql  # half-open


def test_gcp_positive_cost_plus_credits_keep_stable_classes_and_identities():
    rows = [
        gcp_row(),
        gcp_row(line_type="credit", sub_type="SUSTAINED_USAGE_DISCOUNT", amount=Decimal("-6")),
        gcp_row(line_type="credit", sub_type="PROMOTION", amount=Decimal("-4")),
        gcp_row(sub_type="tax", amount=Decimal("2")),
        gcp_row(sub_type="adjustment", amount=Decimal("-1")),
        gcp_row(sub_type="rounding_error", amount=Decimal("0.01")),
    ]
    adapter, _ = gcp([rows])
    lines = lines_of(collect(adapter, spec_for(adapter)))
    assert [(ln.line_kind, ln.charge_class) for ln in lines] == [
        ("gcp:cost:regular", "usage"),
        ("gcp:credit:SUSTAINED_USAGE_DISCOUNT", "discount"),
        ("gcp:credit:PROMOTION", "credit"),
        ("gcp:cost:tax", "tax"),
        ("gcp:cost:adjustment", "adjustment"),
        ("gcp:cost:rounding_error", "rounding"),
    ]
    assert sum(ln.amount for ln in lines) == Decimal("91.01")
    assert {ln.line_key for ln in lines} == {"202609"}
    # The same input always yields the same identities and digests
    again, _ = gcp([rows])
    assert [ln.payload_sha256 for ln in lines_of(collect(again, spec_for(again)))] == [
        ln.payload_sha256 for ln in lines
    ]


def test_gcp_billing_account_and_project_identities_stay_separate():
    adapter, fake = gcp([[]])
    specs = adapter.streams()
    assert {s.billing_account for s in specs} == {f"gcp:ba:{BILLING_ACCOUNT}"}
    assert [s.usage_account for s in specs] == [
        "gcp:project:ml-dev-2",
        "gcp:project:ml-prod-1",
        f"gcp:project:{NO_PROJECT}",
    ]
    collect(adapter, specs[2])
    assert "project.id IS NULL" in fake.queries[0][0]  # taxes and support with no project are not dropped


def test_gcp_conversion_uses_the_export_rate_and_keeps_provenance():
    adapter, _ = gcp(
        [[gcp_row(currency="EUR", amount=Decimal("108"), rate_min=Decimal("1.08"), rate_max=Decimal("1.08"))]]
    )
    [line] = lines_of(collect(adapter, spec_for(adapter)))
    assert (line.currency, line.amount, line.amount_usd, line.fx_rate, line.fx_source) == (
        "EUR",
        Decimal("108"),
        Decimal("100"),
        Decimal("1.08"),
        "gcp_export",
    )


@pytest.mark.parametrize("low,high", [(None, None), (Decimal("1.08"), Decimal("1.09")), (Decimal("0"), Decimal("0"))])
def test_gcp_missing_or_mixed_conversion_stays_unconverted(low, high):
    adapter, _ = gcp([[gcp_row(currency="EUR", rate_min=low, rate_max=high)]])
    [line] = lines_of(collect(adapter, spec_for(adapter)))
    assert (line.amount_usd, line.fx_rate, line.fx_source) == (None, None, None)


@pytest.mark.parametrize(
    "over,code",
    [
        ({"amount": None}, "malformed_row_amount"),
        ({"amount": 1.5}, "malformed_row_amount"),
        ({"amount": "abc"}, "malformed_row_amount"),
        ({"currency": None}, "malformed_row"),
        ({"service_id": ""}, "malformed_row"),
        ({"usage_day": "2026-09-01"}, "malformed_row_date"),
        ({"usage_day": date(2026, 8, 1)}, "malformed_row_date"),
        ({"line_type": "other"}, "malformed_row"),
    ],
)
def test_gcp_malformed_rows_are_incomplete(over, code):
    adapter, _ = gcp([[gcp_row(**over)]])
    incomplete(adapter, spec_for(adapter), code)


def test_gcp_page_failure_and_row_count_mismatch_are_incomplete():
    adapter, _ = gcp([[gcp_row()], [gcp_row(service_id="X")]], fail_at=1)
    assert incomplete(adapter, spec_for(adapter), "provider_page_failed").retryable
    adapter, _ = gcp([[gcp_row()]], total=5)
    assert incomplete(adapter, spec_for(adapter), "row_count_mismatch").retryable


def test_gcp_export_behind_the_window_cannot_prove_silent_days():
    adapter, _ = gcp([[]], export_time=datetime(2026, 9, 2, tzinfo=timezone.utc))  # window ends 09-03
    assert incomplete(adapter, spec_for(adapter), "export_behind_window").retryable


def test_gcp_recent_days_are_estimated():
    recent = DateWindow(date(2026, 9, 29), date(2026, 9, 30))
    adapter, _ = gcp([[gcp_row(usage_day=date(2026, 9, 29))]], export_time=datetime(2026, 9, 30, tzinfo=timezone.utc))
    [line] = lines_of(collect(adapter, spec_for(adapter), recent))
    assert line.is_estimated


@pytest.mark.parametrize(
    "over,code",
    [
        ({"gcp_project_id": "bad`; DROP TABLE x"}, "invalid_export_project"),
        ({"bigquery_dataset": "ds`.x"}, "invalid_dataset"),
        ({"billing_export_table": "users"}, "invalid_table_for_schema"),
        ({"export_schema": "detailed"}, "invalid_table_for_schema"),  # a standard table under the detailed schema
        ({"export_schema": "custom"}, "invalid_export_schema"),
        ({"billing_account_id": "x"}, "invalid_billing_account"),
        ({"project_ids": []}, "invalid_project_inventory"),
        ({"project_ids": ["ok-project-1", "BAD PROJECT"]}, "invalid_project_inventory"),
    ],
)
def test_gcp_dynamic_identifiers_are_validated(over, code):
    with pytest.raises(AdapterConfigError) as err:
        gcp(config=over)
    assert err.value.code == code


def test_gcp_standard_and_detailed_exports_are_distinct_streams():
    standard, _ = gcp()
    detailed, _ = gcp(config={"export_schema": "detailed", "billing_export_table": "gcp_billing_export_resource_v1"})
    assert standard.streams()[0].grouping_version != detailed.streams()[0].grouping_version
    assert standard.streams()[0].vantage != detailed.streams()[0].vantage


def test_gcp_discovery_reports_unexpected_projects():
    adapter, _ = gcp()
    assert adapter.discover(WINDOW).accounts == {"gcp:project:ml-prod-1", "gcp:project:surprise-9"}


# Azure


def azure_payload(
    rows, next_link=None, columns=("Cost", "CostUSD", "UsageDate", "ServiceName", "ChargeType", "Currency")
):
    properties = {"columns": [{"name": c} for c in columns], "rows": rows}
    if next_link:
        properties["nextLink"] = next_link
    return {"properties": properties}


def azure_row(cost=10, usd=10, day="20260901", service="Virtual Machines", charge="Usage", currency="USD"):
    return [cost, usd, int(day), service, charge, currency]


class AzureScript:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)


def azure(responses, config=None):
    script = AzureScript(responses)
    tokens = []

    def token(force):
        tokens.append(force)
        return f"token-{len(tokens)}"

    sleeps = []
    adapter = AzureCostManagementAdapter(
        {"subscription_ids": [SUB_A, SUB_B], **(config or {})},
        http=httpx.Client(transport=httpx.MockTransport(script)),
        token_provider=token,
        sleep=sleeps.append,
        today=lambda: date(2026, 9, 30),
    )
    return adapter, script, tokens, sleeps


def link(sub=SUB_A, skip="abc"):
    return (
        f"https://management.azure.com/subscriptions/{sub}/providers/Microsoft.CostManagement/query"
        f"?api-version=2023-11-01&$skiptoken={skip}"
    )


def test_azure_follows_every_page_and_uses_an_inclusive_provider_end():
    adapter, script, _, _ = azure(
        [
            azure_payload([azure_row()], link(skip="p2")),
            azure_payload([azure_row(service="Storage")], link(skip="p3")),
            azure_payload([azure_row(service="Bandwidth", cost=-1, usd=-1)]),
        ]
    )
    pages = collect(adapter, adapter.streams()[0])
    assert [(p.seq, p.is_last) for p in pages] == [(0, False), (1, False), (2, True)]
    assert sum(ln.amount for ln in lines_of(pages)) == Decimal("19")
    body = script.requests[0].read().decode().replace(" ", "")
    assert '"from":"2026-09-01"' in body and '"to":"2026-09-02"' in body
    assert [r.url.host for r in script.requests] == ["management.azure.com"] * 3


@pytest.mark.parametrize(
    "evil",
    [
        "https://evil.example.com/subscriptions/x/providers/Microsoft.CostManagement/query",
        "http://management.azure.com/subscriptions/" + SUB_A + "/providers/Microsoft.CostManagement/query",
        "https://management.azure.com.evil.example/subscriptions/"
        + SUB_A
        + "/providers/Microsoft.CostManagement/query",
        "https://user:pw@management.azure.com/subscriptions/" + SUB_A + "/providers/Microsoft.CostManagement/query",
        "https://management.azure.com:8443/subscriptions/" + SUB_A + "/providers/Microsoft.CostManagement/query",
        "https://management.azure.com/subscriptions/" + SUB_B + "/providers/Microsoft.CostManagement/query",
        "https://management.azure.com/other",
        12345,
    ],
)
def test_azure_untrusted_continuation_is_refused_before_any_credential_is_sent(evil):
    assert not is_trusted_continuation(evil, f"/subscriptions/{SUB_A}")
    adapter, script, _, _ = azure([azure_payload([azure_row()], evil)])
    incomplete(adapter, adapter.streams()[0], "untrusted_continuation_url")
    assert len(script.requests) == 1  # the bearer token only ever went to the first, trusted request


def test_azure_repeated_continuation_is_incomplete():
    adapter, _, _, _ = azure([azure_payload([], link()), azure_payload([], link())])
    incomplete(adapter, adapter.streams()[0], "repeated_page_token")


def test_azure_401_refreshes_the_token_once():
    adapter, script, tokens, _ = azure([httpx.Response(401), azure_payload([azure_row()])])
    pages = collect(adapter, adapter.streams()[0])
    assert pages[-1].is_last
    assert tokens == [False, True]
    assert script.requests[0].headers["Authorization"] == "Bearer token-1"
    assert script.requests[1].headers["Authorization"] == "Bearer token-2"


def test_azure_repeated_401_is_inaccessible_not_zero():
    adapter, _, _, _ = azure([httpx.Response(401), httpx.Response(401)])
    assert not incomplete(adapter, adapter.streams()[0], "subscription_inaccessible").retryable


def test_azure_429_honours_retry_after_within_a_bound():
    adapter, _, _, sleeps = azure([httpx.Response(429, headers={"Retry-After": "7"}), azure_payload([azure_row()])])
    assert collect(adapter, adapter.streams()[0])[-1].is_last
    assert sleeps == [7.0]
    adapter, script, _, sleeps = azure([httpx.Response(429, headers={"Retry-After": "9999"})])
    assert incomplete(adapter, adapter.streams()[0], "provider_rate_limited").retryable
    assert (sleeps, len(script.requests)) == ([], 1)


def test_azure_503_is_retried_then_succeeds_or_stays_incomplete():
    adapter, _, _, sleeps = azure([httpx.Response(503), httpx.Response(503), azure_payload([azure_row()])])
    assert collect(adapter, adapter.streams()[0])[-1].is_last
    assert sleeps == [1.0, 2.0]
    adapter, script, _, _ = azure([httpx.Response(503)] * 4)
    assert incomplete(adapter, adapter.streams()[0], "provider_unavailable").retryable
    assert len(script.requests) == 4  # bounded


@pytest.mark.parametrize("status", [403, 404])
def test_azure_missing_or_forbidden_subscription_is_never_zero(status):
    adapter, _, _, _ = azure([httpx.Response(status)])
    assert not incomplete(adapter, adapter.streams()[0], "subscription_inaccessible").retryable


def test_azure_redirects_are_not_followed():
    adapter, script, _, _ = azure([httpx.Response(302, headers={"Location": "https://evil.example.com/x"})])
    incomplete(adapter, adapter.streams()[0], "provider_request_rejected")
    assert len(script.requests) == 1


def test_azure_each_subscription_is_a_stream_and_billing_scope_filters_to_it():
    adapter, _, _, _ = azure([])
    assert [s.usage_account for s in adapter.streams()] == [f"azure:sub:{SUB_A}", f"azure:sub:{SUB_B}"]
    billing, script, _, _ = azure(
        [azure_payload([azure_row()])], {"billing_account_id": "BA-1", "use_billing_account_scope": True}
    )
    spec = billing.streams()[1]
    assert spec.scope_type == "azure:billing_account"
    assert "BA-1" in spec.vantage
    # Coverage keys on billing_account: both scopes must name the same account, or they would both count
    assert spec.billing_account == adapter.streams()[1].billing_account == ""
    assert spec.usage_account == adapter.streams()[1].usage_account
    assert spec.vantage != adapter.streams()[1].vantage
    collect(billing, spec)
    assert "/providers/Microsoft.Billing/billingAccounts/BA-1/" in str(script.requests[0].url)
    assert SUB_B in script.requests[0].read().decode()


def test_azure_overlapping_scopes_on_one_connection_are_refused():
    with pytest.raises(AdapterConfigError) as err:
        azure(
            [],
            {
                "billing_account_id": "BA-1",
                "use_billing_account_scope": True,
                "additional_subscription_scopes": [SUB_A],
            },
        )
    assert err.value.code == "overlapping_scopes"


def test_azure_negative_adjustment_and_conversion_details_are_preserved():
    rows = [
        azure_row(cost=-5, usd=-5, charge="Adjustment"),
        azure_row(cost=108, usd=100, service="Storage", currency="EUR"),
        azure_row(cost=50, usd=None, service="Network", currency="EUR"),
        azure_row(cost=0, usd=0, service="Free", currency="EUR"),
    ]
    adapter, _, _, _ = azure([azure_payload(rows)])
    lines = lines_of(collect(adapter, adapter.streams()[0]))
    assert (lines[0].charge_class, lines[0].amount) == ("adjustment", Decimal("-5"))
    assert (lines[1].amount, lines[1].amount_usd, lines[1].fx_rate, lines[1].fx_source) == (
        Decimal("108"),
        Decimal("100"),
        Decimal("1.08"),
        "azure_cost_usd",
    )
    assert (lines[2].amount, lines[2].amount_usd, lines[2].fx_rate) == (Decimal("50"), None, None)
    assert (lines[3].amount_usd, lines[3].fx_source) == (Decimal("0"), "azure_zero_amount")


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"properties": {"rows": []}}, "malformed_response"),
        (azure_payload([], columns=("Cost", "UsageDate")), "missing_column"),
        (azure_payload([azure_row(cost=None)]), "missing_cost_value"),
        (azure_payload([azure_row(cost="abc")]), "malformed_cost_value"),
        (azure_payload([azure_row(day="20260815")]), "day_outside_window"),
        (azure_payload([azure_row(service="")]), "malformed_row"),
    ],
)
def test_azure_malformed_responses_are_incomplete(payload, code):
    adapter, _, _, _ = azure([payload])
    incomplete(adapter, adapter.streams()[0], code)


def test_windows_are_half_open_and_never_empty():
    assert DateWindow(DAY, DAY + timedelta(2)).days == [DAY, DAY + timedelta(1)]
    with pytest.raises(AdapterConfigError):
        DateWindow(DAY, DAY)
