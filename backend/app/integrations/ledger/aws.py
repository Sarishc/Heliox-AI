"""AWS Cost Explorer ledger adapter: one fully paginated query per linked account."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from app.integrations.ledger.base import (
    MAX_PAGES,
    AdapterConfigError,
    DateWindow,
    VERIFIED,
    DAY_ESTIMATED,
    DAY_FINAL,
    DAY_PARTIAL,
    DAY_UNPROVEN,
    Discovery,
    FetchIncomplete,
    ScopeVerdict,
    SourcePage,
    StreamSpec,
)
from app.services.cost_ledger import InvalidCostLine, normalize_line

GROUPING_VERSION = "aws.v1.service+record_type"
METRIC = "UnblendedCost"
ACCOUNT_RE = re.compile(r"^\d{12}$")
THROTTLE_CODES = {"ThrottlingException", "LimitExceededException", "RequestLimitExceeded", "ServiceUnavailable"}
ACCESS_CODES = {"AccessDeniedException", "AccessDenied", "UnauthorizedOperation", "BillExpirationException"}

RECORD_TYPE_CLASSES = {
    "Usage": "usage",
    "DiscountedUsage": "usage",
    "SavingsPlanCoveredUsage": "usage",
    "Credit": "credit",
    "Refund": "refund",
    "Tax": "tax",
    "Support": "support",
    "Fee": "fee",
    "RIFee": "fee",
    "SavingsPlanRecurringFee": "fee",
    "SavingsPlanUpfrontFee": "fee",
    "SavingsPlanNegation": "discount",
    "Enterprise Discount Program Discount": "discount",
    "Private Rate Card Discount": "discount",
    "Bundled Discount": "discount",
    "Rounding": "rounding",
}


def _bucket(service: str) -> str:
    if "EC2" in service or "Elastic Compute" in service:
        return "ec2"
    if "SageMaker" in service:
        return "sagemaker"
    return "aws_other"


def _has_cost(total: Any) -> bool:
    """A day with no groups may report a Total of zero; a non-zero one is cost this query did not break down."""
    if not isinstance(total, Mapping):
        return False
    metric = total.get(METRIC)
    if not isinstance(metric, Mapping):
        return bool(total)
    try:
        return Decimal(str(metric.get("Amount"))) != 0
    except InvalidOperation:
        return True


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        return str(response.get("Error", {}).get("Code", ""))
    return ""


class AwsCostExplorerAdapter:
    """Cost Explorer through a boto3-style client.

    ``linked_account_ids`` is what the customer expects; ``verify_scope`` proves it. The configured payer
    must match the organization's management account as reported by AWS, and a linked account must be
    an active member. Any account can read its organization's management account, but only the
    management account or a delegated administrator can list members, so a member connection can prove
    only itself. Anything unproven is incomplete, never zero. Tag grouping is deliberately not offered:
    tags never decide ownership.
    """

    provider = "aws"

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        client_factory: Callable[[str], Any],
    ):
        self.payer = str(config.get("payer_account_id") or "")
        accounts = config.get("linked_account_ids") or []
        if isinstance(accounts, str):
            accounts = [a.strip() for a in accounts.split(",") if a.strip()]
        self.accounts = sorted(set(accounts))
        if not ACCOUNT_RE.match(self.payer):
            raise AdapterConfigError("invalid_payer_account", "payer_account_id must be 12 digits")
        if not self.accounts or not all(ACCOUNT_RE.match(a) for a in self.accounts):
            raise AdapterConfigError("invalid_linked_accounts", "linked_account_ids must be explicit 12-digit ids")
        self._client_factory = client_factory
        self._caller: Optional[str] = None
        self._provable_from: dict[str, date] = {}  # the first day an empty result can mean zero, per account
        self._joining_day: dict[str, date] = {}  # the day an account joined part of the way through, per account

    def _ce(self) -> Any:
        return self._client_factory("ce")

    def _caller_account(self) -> str:
        if self._caller is None:
            try:
                self._caller = str(self._client_factory("sts").get_caller_identity()["Account"])
            except Exception as exc:
                raise FetchIncomplete("caller_identity_failed", retryable=_is_retryable(exc)) from None
        return self._caller

    def streams(self) -> Sequence[StreamSpec]:
        caller = self._caller_account()
        return [
            StreamSpec(
                provider="aws",
                scope_type="aws:linked_account",
                billing_account=f"aws:payer:{self.payer}",
                usage_account=f"aws:acct:{account}",
                vantage=f"aws:caller:{caller}",
                metric=METRIC,
                grouping_version=GROUPING_VERSION,
                config={"metric": METRIC, "group_by": ["SERVICE", "RECORD_TYPE"]},
            )
            for account in self.accounts
        ]

    def verify_scope(self) -> Mapping[str, ScopeVerdict]:
        caller = self._caller_account()
        self._joining_day = {}
        organizations = self._client_factory("organizations")
        in_organization = True
        try:
            master = str(organizations.describe_organization()["Organization"]["MasterAccountId"])
        except Exception as exc:
            code = _error_code(exc)
            if code == "AWSOrganizationsNotInUseException":
                master, in_organization = caller, False  # a standalone account is its own payer
            elif code in ACCESS_CODES:
                return self._all(ScopeVerdict(False, "payer_unverifiable"))
            elif isinstance(exc, (KeyError, TypeError)):
                return self._all(ScopeVerdict(False, "payer_unverifiable"))
            else:
                return self._all(ScopeVerdict(False, "scope_lookup_failed", _is_retryable(exc)))
        if master != self.payer:
            return self._all(ScopeVerdict(False, "payer_mismatch"))
        joined: dict[str, datetime] = {}
        members = (
            self._organization_members(organizations, joined) if in_organization and caller == self.payer else None
        )
        verdicts: dict[str, ScopeVerdict] = {}
        for account in self.accounts:
            key = f"aws:acct:{account}"
            if account == caller:
                self._provable_from[account] = date.min  # an account's own costs are its own, whatever its organization
            if isinstance(members, ScopeVerdict):
                verdicts[key] = VERIFIED if account == caller else members
            elif members is not None:
                state = members.get(account)
                if state is None:
                    verdicts[key] = ScopeVerdict(False, "account_not_in_organization")
                elif state != "ACTIVE":
                    verdicts[key] = ScopeVerdict(False, "account_not_active")
                else:
                    verdicts[key] = VERIFIED
                    if account != caller:
                        joined_at = joined.get(account)
                        self._provable_from[account] = _first_full_utc_day(joined_at) if joined_at else date.max
                        if joined_at and joined_at.time() != time.min:
                            self._joining_day[account] = joined_at.date()
            elif account == caller:
                verdicts[key] = VERIFIED
            elif not in_organization:
                verdicts[key] = ScopeVerdict(False, "account_not_in_organization")
            else:
                verdicts[key] = ScopeVerdict(False, "account_not_visible_to_caller")
        return verdicts

    def _all(self, verdict: ScopeVerdict) -> dict[str, ScopeVerdict]:
        return {f"aws:acct:{account}": verdict for account in self.accounts}

    def _organization_members(self, organizations: Any, joined: dict[str, datetime]) -> Any:
        """Account id to State from ListAccounts (Status is retired), or a verdict when it cannot be read.

        Also records when each account joined, in UTC: until its first full UTC day after that, this payer's
        bill is not known to hold all of the account's cost.
        """
        members: dict[str, str] = {}
        token: Optional[str] = None
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            try:
                response = organizations.list_accounts(**({"NextToken": token} if token else {}))
            except Exception as exc:
                if _error_code(exc) in ACCESS_CODES:
                    return ScopeVerdict(False, "membership_unverifiable")
                return ScopeVerdict(False, "scope_lookup_failed", _is_retryable(exc))
            for account in response.get("Accounts", []):
                members[str(account.get("Id"))] = str(account.get("State"))
                joined_at = _utc(account.get("JoinedTimestamp"))
                if joined_at is not None:
                    joined[str(account.get("Id"))] = joined_at
            token = response.get("NextToken")
            if not token:
                return members
            if token in seen:
                return ScopeVerdict(False, "scope_lookup_failed")
            seen.add(token)
        return ScopeVerdict(False, "scope_lookup_failed")

    def discover(self, window: DateWindow) -> Discovery:
        if self._caller_account() != self.payer:
            return Discovery(supported=False)  # a member caller cannot list the organization
        found: set[str] = set()
        token: Optional[str] = None
        seen: set[str] = set()
        for _ in range(MAX_PAGES):
            kwargs: dict[str, Any] = {
                "TimePeriod": _period(window),
                "Dimension": "LINKED_ACCOUNT",
                "Context": "COST_AND_USAGE",
            }
            if token:
                kwargs["NextPageToken"] = token
            response = self._call(self._ce().get_dimension_values, kwargs)
            for item in response.get("DimensionValues", []):
                value = item.get("Value")
                if value:
                    found.add(f"aws:acct:{value}")
            token = response.get("NextPageToken")
            if not token:
                return Discovery(accounts=frozenset(found))
            if token in seen:
                raise FetchIncomplete("repeated_page_token")
            seen.add(token)
        raise FetchIncomplete("too_many_pages")

    def fetch(self, spec: StreamSpec, window: DateWindow) -> Iterator[SourcePage]:
        account = spec.usage_account.split(":")[-1]
        caller = self._caller_account()
        if caller != self.payer and caller != account:
            raise FetchIncomplete("account_not_visible_to_caller")
        client = self._ce()
        token: Optional[str] = None
        seen_tokens: set[str] = set()
        seen_days: set[date] = set()
        estimated_days: set[date] = set()
        days_with_lines: set[date] = set()
        expected = set(window.days)
        for seq in range(MAX_PAGES):
            kwargs: dict[str, Any] = {
                "TimePeriod": _period(window),
                "Granularity": "DAILY",
                "Metrics": [METRIC],
                "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "DIMENSION", "Key": "RECORD_TYPE"}],
                "Filter": {"Dimensions": {"Key": "LINKED_ACCOUNT", "Values": [account]}},
            }
            if token:
                kwargs["NextPageToken"] = token
            response = self._call(client.get_cost_and_usage, kwargs)
            lines = []
            for period in response.get("ResultsByTime", []):
                day = _parse_day(period)
                if day not in expected:
                    raise FetchIncomplete("day_outside_window")
                seen_days.add(day)
                estimated = period.get("Estimated")
                if not isinstance(estimated, bool):
                    raise FetchIncomplete("malformed_estimated_flag")
                if estimated:
                    estimated_days.add(day)
                if period.get("Groups"):
                    days_with_lines.add(day)
                for group in period.get("Groups", []):
                    lines.append(_line(group, day, estimated))
                if not period.get("Groups") and _has_cost(period.get("Total")):
                    raise FetchIncomplete("unexpected_ungrouped_total")  # cost with no group cannot be attributed
            token = response.get("NextPageToken")
            if not token:
                if seen_days != expected:
                    raise FetchIncomplete("missing_days")
                provable_from = self._provable_from.get(account, date.max)
                joining_day = self._joining_day.get(account)
                evidence = {}
                for day in window.days:
                    if day == joining_day:  # cost from earlier that day went to the previous payer, or nowhere known
                        evidence[day] = DAY_PARTIAL if day in days_with_lines else DAY_UNPROVEN
                    elif day in estimated_days:
                        evidence[day] = DAY_ESTIMATED
                    else:
                        evidence[day] = DAY_FINAL if day in days_with_lines or day >= provable_from else DAY_UNPROVEN
                yield SourcePage(
                    seq, tuple(lines), is_last=True, watermark=datetime.now(timezone.utc), day_evidence=evidence
                )
                return
            if token in seen_tokens:
                raise FetchIncomplete("repeated_page_token")
            seen_tokens.add(token)
            yield SourcePage(seq, tuple(lines))
        raise FetchIncomplete("too_many_pages")

    def _call(self, method: Callable[..., Any], kwargs: dict[str, Any]) -> Mapping[str, Any]:
        try:
            response = method(**kwargs)
        except Exception as exc:
            code = _error_code(exc)
            if code in ACCESS_CODES:
                raise FetchIncomplete("access_denied") from None
            raise FetchIncomplete("provider_request_failed", retryable=_is_retryable(exc)) from None
        if not isinstance(response, Mapping):
            raise FetchIncomplete("malformed_response")
        return response


def _is_retryable(exc: Exception) -> bool:
    code = _error_code(exc)
    if code:
        return code in THROTTLE_CODES
    return True  # network or SDK failure with no provider verdict


def _utc(joined: Any) -> Optional[datetime]:
    """A timestamp with no UTC offset can't be placed on a UTC day, so it proves nothing, like a missing one."""
    if not isinstance(joined, datetime) or joined.utcoffset() is None:
        return None
    return joined.astimezone(timezone.utc)


def _first_full_utc_day(joined_at: datetime) -> date:
    return joined_at.date() if joined_at.time() == time.min else joined_at.date() + timedelta(days=1)


def _period(window: DateWindow) -> dict[str, str]:
    return {"Start": window.start.isoformat(), "End": window.end.isoformat()}


def _parse_day(period: Mapping[str, Any]) -> date:
    try:
        return date.fromisoformat(period["TimePeriod"]["Start"])
    except (KeyError, TypeError, ValueError):
        raise FetchIncomplete("malformed_time_period") from None


def _line(group: Mapping[str, Any], day: date, estimated: bool):
    keys = group.get("Keys")
    if not isinstance(keys, Sequence) or isinstance(keys, str) or len(keys) != 2 or not all(keys):
        raise FetchIncomplete("malformed_group_keys")
    service, record_type = str(keys[0]), str(keys[1])
    try:
        metric = group["Metrics"][METRIC]
        raw, unit = metric["Amount"], metric["Unit"]
    except (KeyError, TypeError):
        raise FetchIncomplete("missing_cost_value") from None
    if not isinstance(raw, str):
        raise FetchIncomplete("malformed_cost_value")  # never turn a missing amount into zero
    try:
        amount = Decimal(raw).quantize(Decimal("1e-10"))
    except InvalidOperation:
        raise FetchIncomplete("malformed_cost_value") from None
    try:
        return normalize_line(
            usage_date=day,
            line_kind=f"aws:{record_type}"[:48],
            canonical_service=service[:256],
            charge_class=RECORD_TYPE_CLASSES.get(record_type, "other"),
            cost_bucket=_bucket(service),
            currency=unit,
            amount=amount,
            dim_1=service[:256],
            is_estimated=estimated,
        )
    except InvalidCostLine:
        raise FetchIncomplete("malformed_cost_value") from None
