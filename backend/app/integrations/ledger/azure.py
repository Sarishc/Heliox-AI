"""Azure Cost Management ledger adapter: one fully paginated query per subscription, in one billing scope."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence
from urllib.parse import urlsplit

import httpx

from app.integrations.ledger.base import (
    MAX_PAGES,
    AdapterConfigError,
    DateWindow,
    Discovery,
    FetchIncomplete,
    SourcePage,
    StreamSpec,
    is_estimated_day,
)
from app.services.cost_ledger import InvalidCostLine, normalize_line

MANAGEMENT_HOST = "management.azure.com"
API_VERSION = "2023-11-01"
SUBSCRIPTION_RE = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
BILLING_ACCOUNT_RE = re.compile(r"^[0-9A-Za-z:_-]{1,128}$")
MAX_RETRIES = 3
MAX_RETRY_AFTER_SECONDS = 120
SETTLE_DAYS = 3
CHARGE_CLASSES = {
    "usage": "usage",
    "purchase": "fee",
    "refund": "refund",
    "adjustment": "adjustment",
    "tax": "tax",
    "credit": "credit",
    "unusedreservation": "fee",
    "unusedsavingsplan": "fee",
}
BUCKETS = (
    (("virtual machine", "compute"), "azure_vm"),
    (("machine learning",), "azure_ml"),
    (("kubernetes", "container"), "azure_aks"),
    (("batch",), "azure_batch"),
)


def is_trusted_continuation(url: Any, scope: str) -> bool:
    """A continuation link may only go to the management API, within the same scope, over HTTPS."""
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname == MANAGEMENT_HOST
        and port in (None, 443)
        and parts.username is None
        and parts.password is None
        and parts.path.lower().startswith(f"{scope}/providers/microsoft.costmanagement/query".lower())
    )


class AzureCostManagementAdapter:
    """Subscriptions are the expected inventory. An inaccessible subscription is incomplete, never zero.

    A connection observes through either subscription scopes or one billing-account scope. Configuring
    both would observe the same charges twice from one connection, so it is refused. Overlap between
    connections is handled by the ledger: the second view is a witness.
    """

    provider = "azure"

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        http: httpx.Client,
        token_provider: Callable[[bool], str],
        sleep: Callable[[float], None],
        today: Callable[[], date] = lambda: datetime.now(timezone.utc).date(),
    ):
        subscriptions = config.get("subscription_ids") or []
        if isinstance(subscriptions, str):
            subscriptions = [s.strip() for s in subscriptions.split(",") if s.strip()]
        self.subscriptions = sorted({str(s).lower() for s in subscriptions})
        self.billing_account = str(config.get("billing_account_id") or "")
        self.use_billing_scope = bool(config.get("use_billing_account_scope"))
        if not self.subscriptions or not all(SUBSCRIPTION_RE.match(s) for s in self.subscriptions):
            raise AdapterConfigError("invalid_subscription_inventory")
        if self.billing_account and not BILLING_ACCOUNT_RE.match(self.billing_account):
            raise AdapterConfigError("invalid_billing_account")
        if self.use_billing_scope and not self.billing_account:
            raise AdapterConfigError("billing_scope_needs_billing_account")
        if config.get("additional_subscription_scopes") and self.use_billing_scope:
            raise AdapterConfigError("overlapping_scopes", "a connection uses one scope kind, not both")
        self._http = http
        self._token_provider = token_provider
        self._sleep = sleep
        self._today = today
        self._token: Optional[str] = None

    def _scope(self, subscription: str) -> str:
        if self.use_billing_scope:
            return f"/providers/Microsoft.Billing/billingAccounts/{self.billing_account}"
        return f"/subscriptions/{subscription}"

    def streams(self) -> Sequence[StreamSpec]:
        kind = "azure:billing_account" if self.use_billing_scope else "azure:subscription"
        return [
            StreamSpec(
                provider="azure",
                scope_type=kind,
                # Coverage keys on billing_account. A subscription id is globally unique, so every view of it
                # must use the same value here or both views would count; the scope stays in the vantage.
                billing_account="",
                usage_account=f"azure:sub:{subscription}",
                vantage=f"azure:scope:{self._scope(subscription)}",
                metric="ActualCost",
                grouping_version="azure.v1.service+charge_type",
                config={"type": "ActualCost", "api": API_VERSION},
            )
            for subscription in self.subscriptions
        ]

    def discover(self, window: DateWindow) -> Discovery:
        if not self.use_billing_scope:
            return Discovery(supported=False)  # a subscription scope cannot list its siblings
        scope = self._scope("")
        found: set[str] = set()
        body = self._body(window, grouping=["SubscriptionId"], subscription=None)
        for payload in self._pages(scope, body):
            index = _columns(payload)
            if "SubscriptionId" not in index:
                raise FetchIncomplete("missing_column")
            for row in _rows(payload):
                value = _cell(row, index["SubscriptionId"])
                if value:
                    found.add(f"azure:sub:{str(value).lower()}")
        return Discovery(accounts=frozenset(found))

    def fetch(self, spec: StreamSpec, window: DateWindow) -> Iterator[SourcePage]:
        subscription = spec.usage_account.split(":", 2)[-1]
        scope = self._scope(subscription)
        body = self._body(
            window,
            grouping=["ServiceName", "ChargeType", "Currency"],
            subscription=subscription if self.use_billing_scope else None,
        )
        today = self._today()
        previous: Optional[tuple] = None
        seq = -1
        for payload in self._pages(scope, body):
            lines = tuple(self._lines(payload, window, today))
            if previous is not None:
                yield SourcePage(seq, previous)
            previous = lines
            seq += 1
        yield SourcePage(max(seq, 0), previous or (), is_last=True, watermark=datetime.now(timezone.utc))

    def _body(self, window: DateWindow, *, grouping: Sequence[str], subscription: Optional[str]) -> dict[str, Any]:
        dataset: dict[str, Any] = {
            "granularity": "Daily",
            "aggregation": {
                "totalCost": {"name": "Cost", "function": "Sum"},
                "totalCostUSD": {"name": "CostUSD", "function": "Sum"},
            },
            "grouping": [{"type": "Dimension", "name": name} for name in grouping],
        }
        if subscription:
            dataset["filter"] = {
                "dimensions": {"name": "SubscriptionId", "operator": "In", "values": [subscription]},
            }
        return {
            "type": "ActualCost",
            "timeframe": "Custom",
            # Azure's "to" is inclusive; the ledger's window end is exclusive
            "timePeriod": {"from": window.start.isoformat(), "to": (window.end - timedelta(days=1)).isoformat()},
            "dataset": dataset,
        }

    def _pages(self, scope: str, body: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
        url = f"https://{MANAGEMENT_HOST}{scope}/providers/Microsoft.CostManagement/query?api-version={API_VERSION}"
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            payload = self._post(url, body)
            yield payload
            properties = payload.get("properties")
            next_link = properties.get("nextLink") if isinstance(properties, Mapping) else None
            if not next_link:
                return
            if not is_trusted_continuation(next_link, scope):
                raise FetchIncomplete("untrusted_continuation_url")
            if next_link in seen:
                raise FetchIncomplete("repeated_page_token")
            seen.add(next_link)
            url = next_link
        raise FetchIncomplete("too_many_pages")

    def _post(self, url: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        refreshed = False
        for attempt in range(MAX_RETRIES + 1):
            if self._token is None:
                try:
                    self._token = self._token_provider(False)
                except Exception:
                    raise FetchIncomplete("token_request_failed", retryable=True) from None
            try:
                response = self._http.post(url, json=body, headers={"Authorization": f"Bearer {self._token}"})
            except httpx.HTTPError:
                if attempt == MAX_RETRIES:
                    raise FetchIncomplete("provider_request_failed", retryable=True) from None
                self._sleep(2**attempt)
                continue
            status = response.status_code
            if status == 200:
                try:
                    payload = response.json()
                except ValueError:
                    raise FetchIncomplete("malformed_response", retryable=True) from None
                if not isinstance(payload, Mapping):
                    raise FetchIncomplete("malformed_response")
                return payload
            if status == 401 and not refreshed:
                refreshed = True
                try:
                    self._token = self._token_provider(True)
                except Exception:
                    raise FetchIncomplete("token_request_failed", retryable=True) from None
                continue
            if status in (401, 403, 404):
                raise FetchIncomplete("subscription_inaccessible")  # never read as zero spending
            if status == 429 or status >= 500:
                if attempt == MAX_RETRIES:
                    raise FetchIncomplete(
                        "provider_rate_limited" if status == 429 else "provider_unavailable", retryable=True
                    )
                self._sleep(_retry_after(response, attempt))
                continue
            raise FetchIncomplete("provider_request_rejected")
        raise FetchIncomplete("provider_unavailable", retryable=True)

    def _lines(self, payload: Mapping[str, Any], window: DateWindow, today: date) -> list:
        index = _columns(payload)
        required = ("Cost", "UsageDate", "ServiceName", "ChargeType", "Currency")
        if not all(name in index for name in required):
            raise FetchIncomplete("missing_column")
        result = []
        for row in _rows(payload):
            day = _parse_day(_cell(row, index["UsageDate"]))
            if not window.start <= day < window.end:
                raise FetchIncomplete("day_outside_window")
            amount = _amount(_cell(row, index["Cost"]))
            if amount is None:
                raise FetchIncomplete("missing_cost_value")
            service = _cell(row, index["ServiceName"])
            charge = _cell(row, index["ChargeType"])
            currency = _cell(row, index["Currency"])
            if not service or not charge or not currency:
                raise FetchIncomplete("malformed_row")
            usd_raw = _cell(row, index["CostUSD"]) if "CostUSD" in index else None
            usd, rate, source = _usd(amount, str(currency), _amount(usd_raw))
            kind = f"azure:{charge}"
            if len(kind) > 48:
                raise FetchIncomplete("line_kind_too_long")
            try:
                result.append(
                    normalize_line(
                        usage_date=day,
                        line_kind=kind,
                        canonical_service=str(service)[:256],
                        charge_class=CHARGE_CLASSES.get(str(charge).lower(), "other"),
                        cost_bucket=_bucket(str(service)),
                        currency=str(currency),
                        amount=amount,
                        amount_usd=usd,
                        fx_rate=rate,
                        fx_source=source,
                        dim_1=str(service)[:256],
                        is_estimated=is_estimated_day(day, today, SETTLE_DAYS),
                    )
                )
            except InvalidCostLine:
                raise FetchIncomplete("malformed_row") from None
        return result


def _retry_after(response: httpx.Response, attempt: int) -> float:
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        seconds = float(2**attempt)
    if seconds > MAX_RETRY_AFTER_SECONDS:
        raise FetchIncomplete("provider_rate_limited", retryable=True)
    return max(seconds, 0.0)


def _columns(payload: Mapping[str, Any]) -> dict[str, int]:
    properties = payload.get("properties")
    columns = properties.get("columns") if isinstance(properties, Mapping) else None
    if not isinstance(columns, list):
        raise FetchIncomplete("malformed_response")
    return {str(c.get("name")): i for i, c in enumerate(columns) if isinstance(c, Mapping)}


def _rows(payload: Mapping[str, Any]) -> list:
    rows = payload["properties"].get("rows")
    if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
        raise FetchIncomplete("malformed_response")
    return rows


def _cell(row: list, index: int) -> Any:
    return row[index] if index < len(row) else None


def _parse_day(value: Any) -> date:
    text = str(value)
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text[:10])
    except ValueError:
        raise FetchIncomplete("malformed_row_date") from None


def _amount(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise FetchIncomplete("malformed_cost_value") from None
    if not amount.is_finite():
        raise FetchIncomplete("malformed_cost_value")
    return amount.quantize(Decimal("1e-10"))


def _usd(amount: Decimal, currency: str, usd: Optional[Decimal]):
    if currency.upper() == "USD":
        return None, None, None
    if usd is None:
        return None, None, None  # no conversion from the provider: stays unconverted, never presented as USD
    if amount == 0 or usd == 0:
        if amount == 0 and usd == 0:
            return usd, Decimal(1), "azure_zero_amount"  # the rate is immaterial for a zero amount
        return None, None, None
    return usd, (abs(amount) / abs(usd)).quantize(Decimal("1e-12")), "azure_cost_usd"


def _bucket(service: str) -> str:
    lowered = service.lower()
    for needles, bucket in BUCKETS:
        if any(n in lowered for n in needles):
            return bucket
    return "azure_other"
