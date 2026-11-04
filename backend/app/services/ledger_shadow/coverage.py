"""What is actually known about a stream's days, from an explicit starting boundary. Read-only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.ledger.base import DateWindow


@dataclass(frozen=True)
class DayCoverage:
    """One day, with each question answered separately."""

    day: date
    fetched: bool  # a complete fetch was accepted for this day
    provider_state: Optional[str]  # final | estimated | suspect_empty | None when never fetched
    financial_state: str  # complete | estimated | incomplete | not_authoritative | unknown


@dataclass(frozen=True)
class StreamCoverage:
    """Coverage over a window the caller states. ``final_through`` is proven from ``start``, or None.

    Nothing before ``start`` is claimed. The first day that was not fetched, or is not final, ends the range,
    so a stream first fetched in June reports no range at all when asked about May.
    """

    start: date
    final_through: Optional[date]
    financially_complete_through: Optional[date]
    days: tuple[DayCoverage, ...]

    @property
    def missing(self) -> list[date]:
        return [d.day for d in self.days if not d.fetched]


def stream_coverage(session: Session, stream_id: UUID, window: DateWindow) -> StreamCoverage:
    rows = {
        r.usage_date: r
        for r in session.execute(
            text(
                "SELECT sd.usage_date, sd.state, sd.unconverted_count, s.role, c.authoritative_stream_id, "
                "(SELECT count(*) FROM cost_source_conflicts k WHERE k.status = 'open' AND k.team_id = s.team_id "
                "AND k.provider = s.provider AND k.billing_account = s.billing_account "
                "AND k.usage_account = s.usage_account AND k.usage_date = sd.usage_date) AS open_conflicts, "
                "EXISTS (SELECT 1 FROM cost_source_streams o JOIN cost_source_stream_bindings b ON b.stream_id = o.id "
                "AND b.unbound_at IS NULL WHERE o.team_id = s.team_id AND o.provider = s.provider "
                "AND o.usage_account = s.usage_account AND o.role = 'cost' AND o.billing_account <> s.billing_account) "
                "AS ambiguous FROM cost_source_stream_days sd JOIN cost_source_streams s ON s.id = sd.stream_id "
                "LEFT JOIN cost_source_coverage c ON c.team_id = s.team_id AND c.provider = s.provider "
                "AND c.billing_account = s.billing_account AND c.usage_account = s.usage_account "
                "AND c.usage_date = sd.usage_date WHERE sd.stream_id = :s AND sd.usage_date >= :a AND sd.usage_date < :b"
            ),
            {"s": stream_id, "a": window.start, "b": window.end},
        )
    }
    days = []
    final_through = financial_through = None
    final_open = financial_open = True
    for day in window.days:
        row = rows.get(day)
        coverage = _day(day, row, stream_id)
        days.append(coverage)
        final_open = final_open and coverage.provider_state == "final"
        financial_open = financial_open and coverage.financial_state == "complete"
        if final_open:
            final_through = day
        if financial_open:
            financial_through = day
    return StreamCoverage(window.start, final_through, financial_through, tuple(days))


def _day(day: date, row, stream_id: UUID) -> DayCoverage:
    if row is None:
        return DayCoverage(day, False, None, "unknown")
    if row.authoritative_stream_id != stream_id:
        financial = "not_authoritative"
    elif row.state != "final" and row.state != "estimated":
        financial = "incomplete"
    elif row.unconverted_count or row.open_conflicts or row.ambiguous:
        financial = "incomplete"
    elif row.state == "estimated":
        financial = "estimated"
    else:
        financial = "complete"
    return DayCoverage(day, True, row.state, financial)
