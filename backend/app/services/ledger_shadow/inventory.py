"""Expected-account inventory: declared from configuration and held in stream bindings, never read from fetched rows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.ledger.base import DateWindow, StreamSpec
from app.services.cost_ledger import CostLedgerService

INACCESSIBLE_CODES = frozenset({"subscription_inaccessible", "account_not_visible_to_caller", "access_denied"})
AMBIGUOUS_SOURCE = "source_identity_ambiguous"


class InventoryInvalid(Exception):
    """The connection's declared inventory is missing or differs from its durable bindings."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ExpectedStream:
    stream_id: UUID
    spec: StreamSpec


@dataclass
class InventoryReport:
    """What a run expected and what happened, kept apart. An account with no rows is not a zero by itself."""

    expected: list[str] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    published: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    witness: list[str] = field(default_factory=list)
    attribution: list[str] = field(default_factory=list)
    authoritative: list[str] = field(default_factory=list)
    scope_unverified: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    unproven_days: dict[str, list[str]] = field(default_factory=dict)  # account to days nothing can be said about
    invalidated_claims: dict[str, list[dict]] = field(default_factory=dict)  # the earlier claims those days ended
    partial_days: dict[str, list[str]] = field(default_factory=dict)  # account to days whose lines may not be whole
    held_days: dict[str, list[dict]] = field(default_factory=dict)  # provider proved them empty, the ledger holds cost
    discovery: str = "not_attempted"

    def as_dict(self) -> dict:
        return {k: sorted(v) if isinstance(v, list) else v for k, v in asdict(self).items()}


def configure_inventory(
    session: Session, team_id: UUID, connection_id: UUID, specs: Sequence[StreamSpec]
) -> list[UUID]:
    """Explicitly declare a connection's expected streams, and unbind any it no longer expects. Caller commits."""
    service = CostLedgerService(session)
    stream_ids = []
    for spec in specs:
        stream_id = service.register_stream(spec.identity(team_id))
        service.bind_connection(stream_id, connection_id)
        stream_ids.append(stream_id)
    session.execute(
        text(
            "UPDATE cost_source_stream_bindings SET unbound_at = now() WHERE connection_id = :c "
            "AND unbound_at IS NULL AND NOT stream_id = ANY(:keep)"
        ),
        {"c": connection_id, "keep": stream_ids},
    )
    return stream_ids


def ambiguous_streams(session: Session, stream_ids: Sequence[UUID]) -> set[UUID]:
    """Cost streams claiming an account that an active stream in the team bills to a different billing account.

    Coverage is keyed by billing account, so two such streams would both be authoritative for one bill.
    No authority can be chosen here: cost_source_authority is per billing account, so it cannot arbitrate
    between them. Each stays quarantined until a person unbinds the wrong one.
    """
    if not stream_ids:
        return set()
    rows = session.execute(
        text(
            "SELECT s.id FROM cost_source_streams s WHERE s.id = ANY(:ids) AND s.role = 'cost' AND EXISTS ("
            "SELECT 1 FROM cost_source_streams o JOIN cost_source_stream_bindings b ON b.stream_id = o.id "
            "AND b.unbound_at IS NULL WHERE o.team_id = s.team_id AND o.provider = s.provider "
            "AND o.usage_account = s.usage_account AND o.role = 'cost' AND o.billing_account <> s.billing_account)"
        ),
        {"ids": list(stream_ids)},
    )
    return {row.id for row in rows}


def resolve_expected(
    session: Session, team_id: UUID, connection_id: UUID, specs: Sequence[StreamSpec]
) -> list[ExpectedStream]:
    """Match the configured inventory to the durable bindings. Empty or drifted inventory blocks the run."""
    if not specs:
        raise InventoryInvalid("inventory_empty")
    rows = session.execute(
        text(
            "SELECT s.id, s.team_id, s.provider, s.scope_type, s.billing_account, s.usage_account, s.vantage, s.metric, "
            "s.grouping_version, s.role, s.config_sha256 FROM cost_source_stream_bindings b "
            "JOIN cost_source_streams s ON s.id = b.stream_id "
            "WHERE b.connection_id = :c AND b.unbound_at IS NULL AND s.source_kind = 'provider'"
        ),
        {"c": connection_id},
    ).all()
    bound = {}
    for row in rows:
        if row.team_id != team_id:
            raise InventoryInvalid("inventory_tenant_mismatch")
        key = (
            row.provider,
            row.scope_type,
            row.billing_account,
            row.usage_account,
            row.vantage,
            row.metric,
            row.grouping_version,
            row.role,
            bytes(row.config_sha256),
        )
        bound[key] = row.id
    expected = []
    for spec in specs:
        key = (
            spec.provider,
            spec.scope_type,
            spec.billing_account,
            spec.usage_account,
            spec.vantage,
            spec.metric,
            spec.grouping_version,
            spec.role,
            spec.identity(team_id).config_sha256,
        )
        stream_id = bound.pop(key, None)
        if stream_id is None:
            raise InventoryInvalid("inventory_drift")
        expected.append(ExpectedStream(stream_id, spec))
    if bound:
        raise InventoryInvalid("inventory_drift")
    return expected


def manifest(window: DateWindow, expected: Sequence[ExpectedStream]) -> dict:
    """The deterministic request of a run: the same accounts and window always give the same digest."""
    streams = sorted(
        (
            {
                "stream_id": str(e.stream_id),
                "usage_account": e.spec.usage_account,
                "vantage": e.spec.vantage,
                "role": e.spec.role,
            }
            for e in expected
        ),
        key=lambda s: s["stream_id"],
    )
    body = {"window": {"start": window.start.isoformat(), "end": window.end.isoformat()}, "streams": streams}
    body["sha256"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def window_of(run_manifest: Mapping) -> DateWindow:
    from datetime import date

    window = run_manifest["window"]
    return DateWindow(date.fromisoformat(window["start"]), date.fromisoformat(window["end"]))
