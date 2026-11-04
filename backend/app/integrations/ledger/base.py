"""Typed contract shared by the ledger adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, FrozenSet, Iterator, Mapping, Optional, Protocol, Sequence, Tuple
from uuid import UUID

from app.services.cost_ledger import CostLine, StreamIdentity

# What a provider proves about one usage day, independently of whether any cost line exists for it
DAY_FINAL = "final"  # the provider states this day is settled: no lines means a proven zero
DAY_ESTIMATED = "estimated"  # the provider may still revise it: no lines is not a zero
DAY_UNPROVEN = "unproven"  # nothing shows this source would hold the day's cost: no lines means unknown

MAX_PAGES = 1000  # a provider that never stops paginating is an incomplete fetch, not an endless task


class AdapterConfigError(ValueError):
    """The connection's configuration cannot produce a safe inventory or query. Never retried."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class FetchIncomplete(Exception):
    """A source window could not be proven complete. No coverage may be inferred from what was fetched.

    ``code`` is a stable, secret-free reason that is stored on the run. Provider error text is never
    used, because it can echo request details. ``retryable`` says whether a new attempt can help;
    an inaccessible account or malformed data needs a person.
    """

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ScopeLookupDenied(Exception):
    """The provider refused the scope lookup: membership cannot be established."""


class ScopeLookupMissing(Exception):
    """The provider says the account or project does not exist, or is not visible to this credential."""


@dataclass(frozen=True)
class ScopeVerdict:
    """Whether an expected account is proven to belong to this source's scope. Unproven is never zero."""

    verified: bool
    code: Optional[str] = None
    retryable: bool = False


VERIFIED = ScopeVerdict(True)


@dataclass(frozen=True)
class DateWindow:
    """Half-open usage window: ``start`` inclusive, ``end`` exclusive."""

    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise AdapterConfigError("empty_window", "a window needs end > start")

    @property
    def days(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range((self.end - self.start).days)]


@dataclass(frozen=True)
class StreamSpec:
    """One expected way of observing one usage account. Carries no credentials."""

    provider: str
    scope_type: str
    billing_account: str
    usage_account: str
    vantage: str
    metric: str
    grouping_version: str
    config: Mapping[str, Any] = field(default_factory=dict)
    role: str = "cost"

    def identity(self, team_id: UUID) -> StreamIdentity:
        return StreamIdentity(
            team_id=team_id,
            provider=self.provider,
            scope_type=self.scope_type,
            usage_account=self.usage_account,
            vantage=self.vantage,
            metric=self.metric,
            grouping_version=self.grouping_version,
            config=self.config,
            role=self.role,
            billing_account=self.billing_account,
        )


@dataclass(frozen=True)
class SourcePage:
    """One provider page for one stream. ``is_last`` is set only once every page has been read.

    The last page carries ``day_evidence`` for every day of the window. A day it leaves out counts as unproven.
    """

    seq: int
    lines: Tuple[CostLine, ...]
    is_last: bool = False
    watermark: Optional[datetime] = None
    day_evidence: Optional[Mapping[date, str]] = None


@dataclass(frozen=True)
class Discovery:
    """Accounts the provider reports for a scope, to compare against the expected inventory."""

    accounts: FrozenSet[str] = frozenset()
    supported: bool = True


class LedgerAdapter(Protocol):
    """A provider source. ``fetch`` yields pages and raises ``FetchIncomplete`` when it cannot finish."""

    provider: str

    def streams(self) -> Sequence[StreamSpec]:
        """The expected inventory, from explicit configuration; never derived from fetched rows."""
        ...

    def verify_scope(self) -> Mapping[str, ScopeVerdict]:
        """Prove each expected account belongs to this source, from the provider and independently of cost rows.

        An account missing from the result counts as unverified. May raise FetchIncomplete.
        """
        ...

    def discover(self, window: DateWindow) -> Discovery:
        """Accounts visible to the source, reported as unknown when not expected. May raise FetchIncomplete."""
        ...

    def fetch(self, spec: StreamSpec, window: DateWindow) -> Iterator[SourcePage]:
        """Every page of one stream's window. The final page has ``is_last`` set."""
        ...


def is_estimated_day(day: date, today: date, settle_days: int) -> bool:
    """A provider keeps revising recent days: they stay estimated until the settle period has passed."""
    return day >= today - timedelta(days=settle_days)
