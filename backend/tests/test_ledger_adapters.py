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

    def describe_organization(self):
        return {"Organization": {"MasterAccountId": PAYER}}

    def list_accounts(self, **kwargs):
        return {"Accounts": [{"Id": i, "State": "ACTIVE"} for i in (PAYER, MEMBER)]}


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
            project_billing_info=lambda project: {
                "billingAccountName": f"billingAccounts/{BILLING_ACCOUNT}",
                "billingEnabled": True,
            },
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
        f"?api-version=2026-06-01&$skiptoken={skip}"
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
    assert '"from":"2026-09-01T00:00:00Z"' in body and '"to":"2026-09-02T23:59:59Z"' in body
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


# Scope verification, from each provider's own source and never from cost rows


class AwsError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def aws_scope(accounts, *, caller=PAYER, master=PAYER, org_error=None, members=None, list_error=None, pages=None):
    class Client:
        def __call__(self, service):
            return self

        def get_caller_identity(self):
            return {"Account": caller}

        def describe_organization(self):
            if org_error:
                raise org_error
            return {"Organization": {"MasterAccountId": master}}

        def list_accounts(self, **kwargs):
            if list_error:
                raise list_error
            if pages is not None:
                return pages[kwargs.get("NextToken")]
            return {"Accounts": members if members is not None else []}

    return AwsCostExplorerAdapter(
        {"payer_account_id": PAYER, "linked_account_ids": list(accounts)}, client_factory=Client()
    )


def verdict_codes(verdicts):
    return {k.split(":")[-1]: (v.verified, v.code, v.retryable) for k, v in verdicts.items()}


def test_aws_scope_uses_the_organization_and_never_the_configuration():
    members = [
        {"Id": PAYER, "State": "ACTIVE"},
        {"Id": MEMBER, "State": "ACTIVE"},
        {"Id": "333333333333", "State": "SUSPENDED"},
        {"Id": "444444444444", "Status": "ACTIVE"},  # the retired field proves nothing
    ]
    adapter = aws_scope([PAYER, MEMBER, "333333333333", "444444444444", "555555555555"], members=members)
    assert verdict_codes(adapter.verify_scope()) == {
        PAYER: (True, None, False),
        MEMBER: (True, None, False),
        "333333333333": (False, "account_not_active", False),
        "444444444444": (False, "account_not_active", False),
        "555555555555": (False, "account_not_in_organization", False),
    }


def test_aws_scope_reads_every_page_of_members():
    pages = {
        None: {"Accounts": [{"Id": PAYER, "State": "ACTIVE"}], "NextToken": "n2"},
        "n2": {"Accounts": [{"Id": MEMBER, "State": "ACTIVE"}]},
    }
    assert all(v.verified for v in aws_scope([PAYER, MEMBER], pages=pages).verify_scope().values())
    repeated = {None: {"Accounts": [], "NextToken": "n"}, "n": {"Accounts": [], "NextToken": "n"}}
    assert not aws_scope([MEMBER], pages=repeated).verify_scope()[f"aws:acct:{MEMBER}"].verified


@pytest.mark.parametrize(
    "kwargs,code,retryable",
    [
        ({"master": "999999999999"}, "payer_mismatch", False),  # the configured payer is not the real one
        ({"org_error": AwsError("AccessDeniedException")}, "payer_unverifiable", False),
        ({"org_error": AwsError("ThrottlingException")}, "scope_lookup_failed", True),
        ({"org_error": KeyError("Organization")}, "payer_unverifiable", False),
    ],
)
def test_aws_unproven_payer_verifies_nothing(kwargs, code, retryable):
    assert verdict_codes(aws_scope([PAYER, MEMBER], **kwargs).verify_scope()) == {
        PAYER: (False, code, retryable),
        MEMBER: (False, code, retryable),
    }


def test_aws_member_connection_can_prove_only_itself():
    adapter = aws_scope([PAYER, MEMBER], caller=MEMBER)
    assert verdict_codes(adapter.verify_scope()) == {
        PAYER: (False, "account_not_visible_to_caller", False),
        MEMBER: (True, None, False),
    }


def test_aws_payer_without_list_permission_proves_only_itself():
    adapter = aws_scope([PAYER, MEMBER], list_error=AwsError("AccessDeniedException"))
    assert verdict_codes(adapter.verify_scope()) == {
        PAYER: (True, None, False),
        MEMBER: (False, "membership_unverifiable", False),
    }


def test_aws_standalone_account_is_its_own_payer_and_nothing_else():
    adapter = aws_scope([PAYER, MEMBER], org_error=AwsError("AWSOrganizationsNotInUseException"))
    assert verdict_codes(adapter.verify_scope()) == {
        PAYER: (True, None, False),
        MEMBER: (False, "account_not_in_organization", False),
    }
    wrong = aws_scope([MEMBER], caller=MEMBER, org_error=AwsError("AWSOrganizationsNotInUseException"))
    assert verdict_codes(wrong.verify_scope())[MEMBER][1] == "payer_mismatch"  # it claims a payer it does not have


def gcp_scope(lookup, projects=("ml-prod-1", "ml-dev-2")):
    return GcpBillingExportAdapter(
        {**GCP_CONFIG, "project_ids": list(projects)},
        client_factory=FakeBigQuery([]),
        parameters=lambda v: v,
        project_billing_info=lookup,
    )


def test_gcp_scope_comes_from_cloud_billing_not_export_rows():
    from app.integrations.ledger.base import ScopeLookupDenied, ScopeLookupMissing

    answers = {
        "good-project": {"billingAccountName": f"billingAccounts/{BILLING_ACCOUNT}", "billingEnabled": True},
        "moved-project": {"billingAccountName": "billingAccounts/FFFFFF-FFFFFF-FFFFFF", "billingEnabled": True},
        "unlinked-project": {"billingAccountName": "", "billingEnabled": False},
        "disabled-project": {"billingAccountName": f"billingAccounts/{BILLING_ACCOUNT}", "billingEnabled": False},
        "missing-project": ScopeLookupMissing(),
        "denied-project": ScopeLookupDenied(),
        "flaky-project": RuntimeError("503 with detail"),
    }

    def lookup(project):
        answer = answers[project]
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert verdict_codes(gcp_scope(lookup, list(answers)).verify_scope()) == {
        "good-project": (True, None, False),
        "moved-project": (False, "project_on_other_billing_account", False),
        "unlinked-project": (False, "project_has_no_billing_account", False),
        "disabled-project": (False, "project_billing_disabled", False),
        "missing-project": (False, "project_not_found", False),
        "denied-project": (False, "project_inaccessible", False),
        "flaky-project": (False, "scope_lookup_failed", True),
        NO_PROJECT: (True, None, False),
    }


def test_gcp_billing_account_level_rows_need_a_verified_project():
    def lookup(project):
        return {"billingAccountName": "billingAccounts/FFFFFF-FFFFFF-FFFFFF", "billingEnabled": True}

    assert verdict_codes(gcp_scope(lookup).verify_scope())[NO_PROJECT] == (False, "billing_account_unverified", False)


def azure_handler(routes):
    calls = []

    def handler(request):
        calls.append(request)
        for needle, response in routes.items():
            if needle in str(request.url):
                return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)
        raise AssertionError(f"unexpected {request.url}")

    return handler, calls


def azure_scope(routes, config=None):
    handler, calls = azure_handler(routes)
    return (
        AzureCostManagementAdapter(
            {"subscription_ids": [SUB_A], **(config or {})},
            http=httpx.Client(transport=httpx.MockTransport(handler)),
            token_provider=lambda force: "token",
            sleep=lambda s: None,
        ),
        calls,
    )


@pytest.mark.parametrize(
    "response,expected",
    [
        ({"state": "Enabled"}, (True, None, False)),
        ({"state": "Warned"}, (True, None, False)),
        ({"state": "PastDue"}, (True, None, False)),
        ({"state": "Disabled"}, (False, "subscription_not_active", False)),
        ({"state": "Deleted"}, (False, "subscription_not_active", False)),
        ({}, (False, "subscription_not_active", False)),
        (httpx.Response(404), (False, "subscription_inaccessible", False)),
        (httpx.Response(403), (False, "subscription_inaccessible", False)),
    ],
)
def test_azure_subscription_scope_verdicts(response, expected):
    adapter, calls = azure_scope({f"/subscriptions/{SUB_A}": response})
    assert verdict_codes(adapter.verify_scope()) == {SUB_A: expected}
    assert calls[0].method == "GET" and "api-version=2022-12-01" in str(calls[0].url)


BILLING = {"billing_account_id": "BA-1", "use_billing_account_scope": True}
LIST_URL = "https://management.azure.com/providers/Microsoft.Billing/billingAccounts/BA-1/billingSubscriptions?api-version=2024-04-01"


def test_azure_billing_scope_needs_the_billing_accounts_own_list():
    adapter, calls = azure_scope(
        {"billingSubscriptions": {"value": [{"properties": {"subscriptionId": SUB_A.upper()}}]}}, BILLING
    )
    assert adapter.verify_scope()[f"azure:sub:{SUB_A}"].verified
    assert str(calls[0].url) == LIST_URL
    adapter, _ = azure_scope(
        {"billingSubscriptions": {"value": [{"properties": {"subscriptionId": SUB_B}}, {"name": "no-id"}]}}, BILLING
    )
    assert verdict_codes(adapter.verify_scope())[SUB_A] == (False, "subscription_not_in_billing_scope", False)
    adapter, _ = azure_scope({"billingSubscriptions": httpx.Response(403)}, BILLING)
    assert verdict_codes(adapter.verify_scope())[SUB_A] == (False, "billing_scope_unverifiable", False)


def test_azure_billing_list_follows_only_trusted_pages():
    page2 = LIST_URL + "&$skiptoken=2"
    adapter, _ = azure_scope(
        {
            "skiptoken=2": {"value": [{"properties": {"subscriptionId": SUB_A}}]},
            "billingSubscriptions": {"value": [], "nextLink": page2},
        },
        BILLING,
    )
    assert adapter.verify_scope()[f"azure:sub:{SUB_A}"].verified
    adapter, calls = azure_scope(
        {"billingSubscriptions": {"value": [], "nextLink": "https://evil.example.com/billingSubscriptions"}}, BILLING
    )
    assert verdict_codes(adapter.verify_scope())[SUB_A][1] == "untrusted_continuation_url"
    assert len(calls) == 1


# Provider contracts, checked against the published API references. Fake clients prove our side only.


def test_aws_request_matches_the_documented_shape():
    pages = {None: {"ResultsByTime": [period(DAY, []), period(DAY + timedelta(1), [])]}}
    adapter, fake = aws(pages)
    collect(adapter, adapter.streams()[0])
    request = fake.requests[0]
    assert set(request) == {"TimePeriod", "Granularity", "Metrics", "GroupBy", "Filter"}
    assert request["Metrics"] == ["UnblendedCost"]
    assert len(request["GroupBy"]) == 2 and {g["Key"] for g in request["GroupBy"]} == {"SERVICE", "RECORD_TYPE"}


def test_aws_day_with_no_groups_and_a_zero_total_is_empty_but_unbroken_cost_is_not():
    zero = dict(period(DAY, []), Total={"UnblendedCost": {"Amount": "0", "Unit": "USD"}})
    adapter, _ = aws({None: {"ResultsByTime": [zero, period(DAY + timedelta(1), [])]}})
    assert lines_of(collect(adapter, adapter.streams()[0])) == []
    cost = dict(period(DAY, []), Total={"UnblendedCost": {"Amount": "5", "Unit": "USD"}})
    adapter, _ = aws({None: {"ResultsByTime": [cost, period(DAY + timedelta(1), [])]}})
    incomplete(adapter, adapter.streams()[0], "unexpected_ungrouped_total")


def test_aws_unknown_record_type_stays_visible_as_other():
    adapter, _ = aws(
        {None: {"ResultsByTime": [period(DAY, [group("X", "SomeNewType", "1")]), period(DAY + timedelta(1), [])]}}
    )
    [line] = lines_of(collect(adapter, adapter.streams()[0]))
    assert (line.charge_class, line.line_kind) == ("other", "aws:SomeNewType")


def test_gcp_query_uses_documented_columns_and_bound_parameters():
    from app.integrations.ledger.gcp import QUERY

    documented = (
        "billing_account_id",
        "usage_start_time",
        "service.id",
        "service.description",
        "cost_type",
        "currency",
        "invoice.month",
        "currency_conversion_rate",
        "credits",
        "export_time",
        "credit.type",
        "credit.amount",
    )
    for column in documented:
        assert column in QUERY, column
    for parameter in ("@billing_account", "@start_date", "@end_date"):
        assert parameter in QUERY
    adapter, fake = gcp([[]])
    collect(adapter, spec_for(adapter))
    sql = fake.queries[0][0]
    assert "billing-admin-1.billing_export.gcp_billing_export_v1_0A1B2C_3D4E5F_6A7B8C" in sql
    assert "project.id = @project" in sql
    assert "ml-prod-1" not in sql and BILLING_ACCOUNT not in sql  # values only ever arrive as parameters


def test_gcp_rounding_spelling_and_unknown_cost_types():
    adapter, _ = gcp([[gcp_row(sub_type="rounding error"), gcp_row(sub_type="brand_new", service_id="B")]])
    lines = lines_of(collect(adapter, spec_for(adapter)))
    assert [ln.charge_class for ln in lines] == ["rounding", "other"]


def test_azure_request_respects_documented_limits():
    adapter, script, _, _ = azure([azure_payload([azure_row()])])
    collect(adapter, adapter.streams()[0])
    import json as _json

    body = _json.loads(script.requests[0].read())
    assert body["type"] == "ActualCost" and body["timeframe"] == "Custom"
    assert len(body["dataset"]["grouping"]) <= 2 and len(body["dataset"]["aggregation"]) <= 2
    assert {a["function"] for a in body["dataset"]["aggregation"].values()} == {"Sum"}
    assert all(g["type"] == "Dimension" for g in body["dataset"]["grouping"])
    assert "api-version=2026-06-01" in str(script.requests[0].url)


def test_azure_documented_rate_limit_header_is_honoured():
    adapter, _, _, sleeps = azure(
        [
            httpx.Response(429, headers={"x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after": "11"}),
            azure_payload([azure_row()]),
        ]
    )
    assert collect(adapter, adapter.streams()[0])[-1].is_last
    assert sleeps == [11.0]


def test_azure_no_content_is_not_read_as_zero():
    adapter, _, _, _ = azure([httpx.Response(204)])
    incomplete(adapter, adapter.streams()[0], "provider_no_content")


# Factory


def test_factory_selects_each_adapter_and_uses_only_injected_clients(caplog):
    from app.integrations.ledger.factory import ClientFactories, build_adapter

    made = []
    secret = "wJalr-SECRET-do-not-log-000000000000000000"

    class Session_:
        def client(self, service):
            made.append(service)
            return FakeAws({})

    def aws_session(config):
        assert config["aws_secret_access_key"] == secret
        return Session_()

    clients = ClientFactories(
        aws_session=aws_session,
        bigquery_client=lambda c: FakeBigQuery([]),
        bigquery_parameters=lambda v: v,
        billing_session=lambda c: None,
        azure_credential=lambda c: None,
        http_client=lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))),
    )
    aws_adapter = build_adapter(
        "aws",
        {
            "aws_access_key_id": "AKIAEXAMPLE",
            "aws_secret_access_key": secret,
            "payer_account_id": PAYER,
            "linked_account_ids": PAYER,
        },
        clients,
    )
    assert isinstance(aws_adapter, AwsCostExplorerAdapter) and made == []  # nothing connects until it is needed
    specs = aws_adapter.streams()
    assert made == ["sts"]
    assert secret not in str(specs) and secret not in caplog.text
    gcp_adapter = build_adapter(
        "gcp_billing_bigquery", {**GCP_CONFIG, "service_account_json": '{"type": "service_account"}'}, clients
    )
    assert isinstance(gcp_adapter, GcpBillingExportAdapter)
    azure_adapter = build_adapter(
        "azure",
        {"azure_tenant_id": "t", "azure_client_id": "c", "azure_client_secret": secret, "subscription_ids": [SUB_A]},
        clients,
    )
    assert isinstance(azure_adapter, AzureCostManagementAdapter)
    assert secret not in str(azure_adapter.streams())


@pytest.mark.parametrize(
    "provider,config,code",
    [
        ("stripe", {}, "unsupported_provider"),
        ("gcp", {"service_account_json": "{}"}, "unsupported_provider"),
        ("aws", {"aws_access_key_id": "x"}, "missing_credentials"),
        ("gcp_billing_bigquery", {}, "missing_credentials"),
        ("gcp_billing_bigquery", {"service_account_json": "not json"}, "invalid_credentials"),
        ("gcp_billing_bigquery", {"service_account_json": "[1]"}, "invalid_credentials"),
        ("azure", {"azure_tenant_id": "t", "azure_client_id": "c"}, "missing_credentials"),
    ],
)
def test_factory_refuses_bad_configuration_before_any_client_exists(provider, config, code):
    from app.integrations.ledger.factory import ClientFactories, build_adapter

    def forbidden(*args):
        raise AssertionError("no client may be created")

    clients = ClientFactories(forbidden, forbidden, forbidden, forbidden, forbidden, forbidden)
    with pytest.raises(AdapterConfigError) as err:
        build_adapter(provider, config, clients)
    assert err.value.code == code


def test_factory_billing_lookup_maps_statuses_and_azure_tokens_refresh():
    from app.integrations.ledger.base import ScopeLookupDenied, ScopeLookupMissing
    from app.integrations.ledger.factory import _azure_tokens, _project_billing_lookup

    class Response:
        def __init__(self, status):
            self.status_code = status

        def json(self):
            return {"billingEnabled": True}

    urls = []

    def session_with(status):
        class S:
            def get(self, url, timeout):
                urls.append(url)
                return Response(status)

        return lambda: S()

    assert _project_billing_lookup(session_with(200))("ml-prod-1") == {"billingEnabled": True}
    assert urls == ["https://cloudbilling.googleapis.com/v1/projects/ml-prod-1/billingInfo"]
    with pytest.raises(ScopeLookupDenied):
        _project_billing_lookup(session_with(403))("ml-prod-1")
    with pytest.raises(ScopeLookupMissing):
        _project_billing_lookup(session_with(404))("ml-prod-1")
    with pytest.raises(RuntimeError):
        _project_billing_lookup(session_with(500))("ml-prod-1")
    with pytest.raises(ScopeLookupMissing):  # an invalid id never reaches a URL
        _project_billing_lookup(session_with(200))("../../evil")

    created = []

    class Credential:
        def __init__(self):
            created.append(self)

        def get_token(self, scope):
            assert scope == "https://management.azure.com/.default"
            return type("T", (), {"token": f"token-{len(created)}"})

    tokens = _azure_tokens(Credential)
    assert (tokens(False), tokens(False), tokens(True)) == ("token-1", "token-1", "token-2")
