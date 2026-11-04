"""GCP BigQuery billing export ledger adapter: cost and credit lines, every result page, one project per stream."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from app.integrations.ledger.base import (
    DAY_ESTIMATED,
    DAY_FINAL,
    DAY_UNPROVEN,
    VERIFIED,
    AdapterConfigError,
    DateWindow,
    Discovery,
    FetchIncomplete,
    ScopeLookupDenied,
    ScopeLookupMissing,
    ScopeVerdict,
    SourcePage,
    StreamSpec,
    is_estimated_day,
)
from app.services.cost_ledger import InvalidCostLine, normalize_line

PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
DATASET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
BILLING_ACCOUNT_RE = re.compile(r"^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$")
TABLE_RES = {
    "standard": re.compile(r"^gcp_billing_export_v1(_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{6})?$"),
    "detailed": re.compile(r"^gcp_billing_export_resource_v1(_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{6}_[0-9A-Fa-f]{6})?$"),
}
NO_PROJECT = "__billing_account__"  # taxes and support carry no project; they must not be dropped
SETTLE_DAYS = 3
INVOICE_CLOSE_DAYS = 5  # a heuristic, not a provider guarantee: the docs promise no delivery or correction deadline
# The schema describes cost_type as "regular, tax, adjustment, or rounding error"; the stored spelling of the last
# is not stated, so both are accepted. An unknown value stays visible as "other".
COST_TYPE_CLASSES = {
    "regular": "usage",
    "tax": "tax",
    "adjustment": "adjustment",
    "rounding_error": "rounding",
    "rounding error": "rounding",
}
DISCOUNT_CREDITS = {
    "SUSTAINED_USAGE_DISCOUNT",
    "COMMITTED_USAGE_DISCOUNT",
    "COMMITTED_USAGE_DISCOUNT_DOLLAR_BASE",
    "DISCOUNT",
    "SUBSCRIPTION_BENEFIT",
}

# Grouped to the same grain for both export schemas, so a detailed export never multiplies a charge by
# resource. Labels are not selected: they never decide ownership. Values are bound parameters; the
# table name is interpolated only after its parts pass the validation in __init__.
QUERY = """
WITH base AS (
  SELECT DATE(usage_start_time) AS usage_day, service.id AS service_id, service.description AS service_name,
         cost_type, currency, invoice.month AS invoice_month, cost, currency_conversion_rate, credits, export_time
  FROM `{table}`
  WHERE billing_account_id = @billing_account
    AND DATE(usage_start_time) >= @start_date AND DATE(usage_start_time) < @end_date
    AND {project_filter}
)
SELECT usage_day, service_id, service_name, 'cost' AS line_type, cost_type AS sub_type, currency, invoice_month,
       SUM(CAST(cost AS NUMERIC)) AS amount, MIN(currency_conversion_rate) AS rate_min,
       MAX(currency_conversion_rate) AS rate_max, MAX(export_time) AS last_export
FROM base GROUP BY usage_day, service_id, service_name, sub_type, currency, invoice_month
UNION ALL
SELECT usage_day, service_id, service_name, 'credit' AS line_type, credit.type AS sub_type, currency, invoice_month,
       SUM(CAST(credit.amount AS NUMERIC)) AS amount, MIN(currency_conversion_rate) AS rate_min,
       MAX(currency_conversion_rate) AS rate_max, MAX(export_time) AS last_export
FROM base, UNNEST(credits) AS credit GROUP BY usage_day, service_id, service_name, sub_type, currency, invoice_month
ORDER BY usage_day, service_id, line_type, sub_type, currency, invoice_month
"""

DISCOVERY_QUERY = """
SELECT DISTINCT project.id AS project_id FROM `{table}`
WHERE billing_account_id = @billing_account
  AND DATE(usage_start_time) >= @start_date AND DATE(usage_start_time) < @end_date
  AND project.id IS NOT NULL
"""


class GcpBillingExportAdapter:
    """A day is known only from this project's own rows. A day with no rows is unknown, never zero.

    Cloud Billing says which billing account a project is on now, not which it was on then, and a recent
    export_time from other rows says nothing about this project. A project that moved here last month has no rows
    for earlier days in this export whatever it spent. No provider API offers that history, so a genuine zero can't
    be proven here: a project with truly no cost and no rows stays unknown. A zero is proven only by rows that sum
    to it. A fresh export is still required, because without it even days with rows may be partial.
    """

    provider = "gcp"

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        client_factory: Callable[[], Any],
        parameters: Callable[[Sequence[tuple[str, str, Any]]], Any],
        project_billing_info: Callable[[str], Mapping[str, Any]],
        today: Callable[[], date] = lambda: datetime.now(timezone.utc).date(),
    ):
        self.export_project = str(config.get("gcp_project_id") or "")
        self.dataset = str(config.get("bigquery_dataset") or "")
        self.table = str(config.get("billing_export_table") or "")
        self.schema = str(config.get("export_schema") or "standard")
        self.billing_account = str(config.get("billing_account_id") or "")
        projects = config.get("project_ids") or []
        if isinstance(projects, str):
            projects = [p.strip() for p in projects.split(",") if p.strip()]
        self.projects = sorted(set(projects))
        if not PROJECT_RE.match(self.export_project):
            raise AdapterConfigError("invalid_export_project")
        if not DATASET_RE.match(self.dataset):
            raise AdapterConfigError("invalid_dataset")
        if self.schema not in TABLE_RES:
            raise AdapterConfigError("invalid_export_schema")
        if not TABLE_RES[self.schema].match(self.table):
            raise AdapterConfigError("invalid_table_for_schema")
        if not BILLING_ACCOUNT_RE.match(self.billing_account):
            raise AdapterConfigError("invalid_billing_account")
        if not self.projects or not all(PROJECT_RE.match(p) for p in self.projects):
            raise AdapterConfigError("invalid_project_inventory")
        self._client_factory = client_factory
        self._parameters = parameters
        self._project_billing_info = project_billing_info
        self._today = today

    @property
    def _table_ref(self) -> str:
        return f"{self.export_project}.{self.dataset}.{self.table}"

    def streams(self) -> Sequence[StreamSpec]:
        return [
            StreamSpec(
                provider="gcp",
                scope_type="gcp:billing_export",
                billing_account=f"gcp:ba:{self.billing_account}",
                usage_account=f"gcp:project:{project}",
                vantage=f"gcp:table:{self._table_ref}",  # copied export tables are separate witnesses
                metric="cost",
                grouping_version=f"gcp.v1.{self.schema}.service+cost_type+credit_type+invoice",
                config={"export_schema": self.schema},
            )
            for project in [*self.projects, NO_PROJECT]
        ]

    def verify_scope(self) -> Mapping[str, ScopeVerdict]:
        verdicts = {f"gcp:project:{project}": self._verify_project(project) for project in self.projects}
        # Rows with no project belong to the billing account: provable only through a project shown to be on it
        any_verified = any(v.verified for v in verdicts.values())
        verdicts[f"gcp:project:{NO_PROJECT}"] = (
            VERIFIED if any_verified else ScopeVerdict(False, "billing_account_unverified")
        )
        return verdicts

    def _verify_project(self, project: str) -> ScopeVerdict:
        try:
            info = self._project_billing_info(project)
        except ScopeLookupMissing:
            return ScopeVerdict(False, "project_not_found")
        except ScopeLookupDenied:
            return ScopeVerdict(False, "project_inaccessible")
        except Exception:
            return ScopeVerdict(False, "scope_lookup_failed", retryable=True)
        account = info.get("billingAccountName")
        if not account:
            return ScopeVerdict(False, "project_has_no_billing_account")
        if account != f"billingAccounts/{self.billing_account}":
            return ScopeVerdict(False, "project_on_other_billing_account")
        if info.get("billingEnabled") is not True:
            return ScopeVerdict(False, "project_billing_disabled")
        return VERIFIED

    def discover(self, window: DateWindow) -> Discovery:
        rows = self._rows(DISCOVERY_QUERY.format(table=self._table_ref), self._common(window))
        found = set()
        for page in rows.pages:
            for row in page:
                found.add(f"gcp:project:{_get(row, 'project_id')}")
        return Discovery(accounts=frozenset(found))

    def fetch(self, spec: StreamSpec, window: DateWindow) -> Iterator[SourcePage]:
        project = spec.usage_account.split(":", 2)[-1]
        params = self._common(window)
        if project == NO_PROJECT:
            project_filter = "project.id IS NULL"
        else:
            project_filter = "project.id = @project"
            params.append(("project", "STRING", project))
        rows = self._rows(QUERY.format(table=self._table_ref, project_filter=project_filter), params)
        today = self._today()
        fetched = 0
        days_with_rows: dict[date, bool] = {}  # day to whether any of its rows is still estimated
        watermark: Optional[datetime] = None
        batch: list = []
        seq = 0
        try:
            for page in rows.pages:
                if batch or seq:
                    yield SourcePage(seq - 1, tuple(batch))
                batch = []
                for row in page:
                    fetched += 1
                    line, exported = self._line(row, window, today)
                    batch.append(line)
                    days_with_rows[line.usage_date] = days_with_rows.get(line.usage_date, False) or line.is_estimated
                    if exported is not None and (watermark is None or exported > watermark):
                        watermark = exported
                seq += 1
        except FetchIncomplete:
            raise
        except Exception:
            raise FetchIncomplete("provider_page_failed", retryable=True) from None
        total = getattr(rows, "total_rows", None)
        if total is not None and total != fetched:
            raise FetchIncomplete("row_count_mismatch", retryable=True)
        self._require_export_caught_up(window, watermark)
        evidence = {
            day: (DAY_ESTIMATED if days_with_rows[day] else DAY_FINAL) if day in days_with_rows else DAY_UNPROVEN
            for day in window.days
        }
        yield SourcePage(max(seq - 1, 0), tuple(batch), is_last=True, watermark=watermark, day_evidence=evidence)

    def _require_export_caught_up(self, window: DateWindow, watermark: Optional[datetime]) -> None:
        """A silent day is a zero only once the export has moved past it, in this table for any project."""
        rows = self._rows(
            f"SELECT MAX(export_time) AS last_export FROM `{self._table_ref}` WHERE billing_account_id = @billing_account",
            [("billing_account", "STRING", self.billing_account)],
        )
        latest = None
        try:
            for page in rows.pages:
                for row in page:
                    latest = _get(row, "last_export")
        except Exception:
            raise FetchIncomplete("provider_page_failed", retryable=True) from None
        latest = latest or watermark
        if not isinstance(latest, datetime):
            raise FetchIncomplete("export_watermark_unknown", retryable=True)
        end = datetime(window.end.year, window.end.month, window.end.day, tzinfo=timezone.utc)
        aware = latest if latest.tzinfo else latest.replace(tzinfo=timezone.utc)
        if aware < end:
            raise FetchIncomplete("export_behind_window", retryable=True)

    def _common(self, window: DateWindow) -> list[tuple[str, str, Any]]:
        return [
            ("billing_account", "STRING", self.billing_account),
            ("start_date", "DATE", window.start),
            ("end_date", "DATE", window.end),
        ]

    def _rows(self, sql: str, params: Sequence[tuple[str, str, Any]]) -> Any:
        try:
            return self._client_factory().query(sql, job_config=self._parameters(params)).result()
        except Exception:
            raise FetchIncomplete("provider_request_failed", retryable=True) from None

    def _line(self, row: Any, window: DateWindow, today: date):
        day = _get(row, "usage_day")
        if not isinstance(day, date) or not window.start <= day < window.end:
            raise FetchIncomplete("malformed_row_date")
        service_id, service_name = _get(row, "service_id"), _get(row, "service_name")
        line_type, sub_type = _get(row, "line_type"), _get(row, "sub_type")
        currency, invoice = _get(row, "currency"), _get(row, "invoice_month")
        if not service_id or not currency or not invoice or line_type not in ("cost", "credit") or not sub_type:
            raise FetchIncomplete("malformed_row")
        raw = _get(row, "amount")
        if isinstance(raw, float) or raw is None:
            raise FetchIncomplete("malformed_row_amount")  # NUMERIC arrives exact; a float or NULL is not money
        try:
            amount = Decimal(str(raw)).quantize(Decimal("1e-10"))
        except InvalidOperation:
            raise FetchIncomplete("malformed_row_amount") from None
        if line_type == "cost":
            kind = f"gcp:cost:{sub_type}"
            charge_class = COST_TYPE_CLASSES.get(str(sub_type), "other")
        else:
            kind = f"gcp:credit:{sub_type}"
            charge_class = "discount" if str(sub_type) in DISCOUNT_CREDITS else "credit"
        if len(kind) > 48:
            raise FetchIncomplete("line_kind_too_long")
        usd, rate, source = _usd(amount, str(currency), _get(row, "rate_min"), _get(row, "rate_max"))
        exported = _get(row, "last_export")
        try:
            line = normalize_line(
                usage_date=day,
                line_kind=kind,
                canonical_service=str(service_id)[:256],
                charge_class=charge_class,
                cost_bucket=str(service_name or service_id)[:100],
                currency=str(currency),
                amount=amount,
                amount_usd=usd,
                fx_rate=rate,
                fx_source=source,
                dim_1=str(service_id)[:256],
                line_key=str(invoice)[:128],
                is_estimated=_still_estimated(day, today),
            )
        except InvalidCostLine:
            raise FetchIncomplete("malformed_row") from None
        return line, exported if isinstance(exported, datetime) else None


def _still_estimated(day: date, today: date) -> bool:
    """A day stays estimated until its usage month should have been invoiced. Final does not mean immutable:
    a late correction after that is still applied, with its audit trail, on the next re-fetch of the window.
    """
    next_month = date(day.year + day.month // 12, day.month % 12 + 1, 1)
    return is_estimated_day(day, today, SETTLE_DAYS) or today < next_month + timedelta(days=INVOICE_CLOSE_DAYS)


def _usd(amount: Decimal, currency: str, rate_min: Any, rate_max: Any):
    """Convert with the export's own rate (billing-currency units per USD). A missing or mixed rate stays unconverted."""
    if currency.upper() == "USD":
        return None, None, None
    if rate_min is None or rate_max is None or isinstance(rate_min, bool):
        return None, None, None
    try:
        low, high = Decimal(str(rate_min)), Decimal(str(rate_max))
    except InvalidOperation:
        return None, None, None
    if low != high or low <= 0:
        return None, None, None
    rate = low.quantize(Decimal("1e-12"))
    if rate <= 0:
        return None, None, None
    return (amount / rate).quantize(Decimal("1e-10")), rate, "gcp_export"


def _get(row: Any, name: str) -> Any:
    try:
        return row[name]
    except (KeyError, TypeError, IndexError):
        return None
