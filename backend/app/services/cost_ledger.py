"""
Shadow-only cost ledger service (Step 6E), on the migration 038 tables.

Stores provider cost lines idempotently, keeps one authoritative cost stream per usage account and
day, quarantines disagreeing witnesses, and computes shadow totals. It never writes cost_snapshots,
usage_events, usage_daily_rollups or stripe_meter_exports, and the database gates keep everything it
records non-billable.

Contract
--------
- Every method runs in the caller's ``Session`` and never commits or rolls back: the caller owns the
  transaction. ``publish`` writes all of its changes in that one transaction, so a failure (raise)
  leaves nothing behind once the caller rolls back.
- Lock order inside ``publish`` and ``set_authority``: the connection's lease row (``FOR UPDATE``,
  publish only), then a transaction-scoped advisory lock on the team. Every ledger write for a team
  therefore happens one at a time; unique constraints remain the backstop.
- Tenancy comes only from the sync run's connection: the stream must belong to the connection's
  team and be bound to that connection. Labels, tags and other provider metadata are data only.
- Money is ``Decimal`` end to end (NUMERIC in the database). ``float`` amounts are rejected. Totals
  are rounded once, to cents, when a ``ShadowTotal`` is produced.

Publication semantics (per stream and usage day, ``Publication.window_start`` inclusive to
``window_end`` exclusive):
- incomplete fetch: nothing is written, coverage does not move (``outcome.incomplete``);
- a day whose newer fetch was already published is skipped (``stale``);
- a complete but suddenly empty day that previously had cost is held (``held``), nothing retired;
- otherwise lines are upserted (inserted / corrected / unchanged / reappeared), missing lines are
  retired (``retired``), and one immutable observation is written per change or confirmation;
- cost streams update coverage: a configured authority wins, otherwise the first stream to publish
  the account-day; every other stream is a witness, and a disagreeing witness opens a quarantined
  conflict (``quarantined``). Authority never changes automatically;
- attribution streams never affect coverage, totals or billing; they are reconciled per service.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable, Mapping, Optional, Sequence
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CHARGE_CLASSES = frozenset(
    {"usage", "credit", "refund", "discount", "tax", "fee", "support", "adjustment", "rounding", "other"}
)
AMOUNT_QUANTUM = Decimal("1e-10")
CENT = Decimal("0.01")
WITNESS_TOLERANCE_USD = Decimal("0.005")
LEASE_TTL = timedelta(minutes=5)


class LedgerError(Exception):
    """Base class: the publication was refused and nothing was written."""


class LedgerDisabled(LedgerError):
    """The team's ledger mode is 'off' (no settings row)."""


class LedgerFenced(LedgerError):
    """The run no longer holds the connection's lease (lost, expired or taken over)."""


class TenantMismatch(LedgerError):
    """The stream does not belong to the connection's team, or is not bound to the connection."""


class InvalidCostLine(LedgerError, ValueError):
    """A cost line or publication is malformed (float money, bad currency, duplicate identity ...)."""


class AlreadyPublished(LedgerError):
    """This run already published this stream."""


# ── Types ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StreamIdentity:
    """One way of observing one usage account. ``config`` is hashed into the stream identity."""

    team_id: UUID
    provider: str
    scope_type: str
    usage_account: str
    vantage: str
    metric: str
    grouping_version: str
    config: Mapping[str, Any]
    role: str = "cost"
    source_kind: str = "provider"
    billing_account: str = ""

    @property
    def config_sha256(self) -> bytes:
        return hashlib.sha256(json.dumps(self.config, sort_keys=True, separators=(",", ":")).encode()).digest()


@dataclass(frozen=True)
class CostLine:
    """One normalized provider cost line for one usage day."""

    usage_date: date
    line_kind: str
    canonical_service: str
    charge_class: str
    cost_bucket: str
    currency: str
    amount: Decimal
    amount_usd: Optional[Decimal]
    dim_1: str = ""
    dim_2: str = ""
    line_key: str = ""
    fx_rate: Optional[Decimal] = None
    fx_source: Optional[str] = None
    is_estimated: bool = False

    @property
    def identity(self) -> tuple:
        return (self.usage_date, self.dim_1, self.dim_2, self.line_kind, self.line_key, self.currency)


@dataclass(frozen=True)
class Publication:
    run_id: UUID
    attempt: int
    fencing_token: int
    stream_id: UUID
    window_start: date
    window_end: date
    lines: Sequence[CostLine]
    complete: bool


@dataclass
class PublishOutcome:
    fetched: int = 0
    inserted: int = 0
    corrected: int = 0
    unchanged: int = 0
    reappeared: int = 0
    retired: int = 0
    held: int = 0
    stale: int = 0
    quarantined: int = 0
    incomplete: bool = False
    published_days: list[date] = field(default_factory=list)
    new_shadow_facts: int = 0


@dataclass(frozen=True)
class Contribution:
    """One ledger record's input to the shadow aggregation."""

    usage_date: date
    provider: str
    cost_bucket: str
    amount_usd: Optional[Decimal]
    present: bool
    authoritative: bool
    source_kind: str
    coverage_state: Optional[str]


@dataclass(frozen=True)
class ShadowTotal:
    usage_date: date
    provider: str
    cost_bucket: str
    amount_usd: Optional[Decimal]  # known USD, rounded to cents; None when nothing is known yet
    completeness: str  # complete | estimated | incomplete
    counted: int
    unconverted: int
    blocked: int


# ── Normalization ────────────────────────────────────────────────────────────────


def _money(value: Any, field_name: str) -> Decimal:
    if isinstance(value, (float, bool)):
        raise InvalidCostLine(f"{field_name} must be a Decimal, int or numeric string, not {type(value).__name__}")
    try:
        result = Decimal(str(value))
    except Exception as exc:  # decimal.InvalidOperation
        raise InvalidCostLine(f"{field_name} is not a number") from exc
    if not result.is_finite():
        raise InvalidCostLine(f"{field_name} must be finite")
    return result


def normalize_line(
    *,
    usage_date: date,
    line_kind: str,
    canonical_service: str,
    charge_class: str,
    cost_bucket: str,
    currency: str,
    amount: Any,
    amount_usd: Any = None,
    fx_rate: Any = None,
    fx_source: Optional[str] = None,
    dim_1: str = "",
    dim_2: str = "",
    line_key: str = "",
    is_estimated: bool = False,
) -> CostLine:
    """Validate one provider line. USD is never assumed for another currency."""
    currency = (currency or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise InvalidCostLine("currency must be a 3-letter ISO code")
    if charge_class not in CHARGE_CLASSES:
        raise InvalidCostLine(f"unknown charge_class {charge_class!r}")
    if not canonical_service:
        raise InvalidCostLine("canonical_service is required")
    amount_d = _money(amount, "amount").quantize(AMOUNT_QUANTUM)
    if currency == "USD":
        if fx_rate is not None or (amount_usd is not None and _money(amount_usd, "amount_usd") != amount_d):
            raise InvalidCostLine("USD lines carry no conversion")
        usd, rate, source = amount_d, None, None
    elif amount_usd is None and fx_rate is None:
        usd, rate, source = None, None, None  # unconverted: never presented as USD
    else:
        if amount_usd is None or fx_rate is None or not fx_source:
            raise InvalidCostLine("a converted line needs amount_usd, fx_rate and fx_source")
        rate = _money(fx_rate, "fx_rate")
        if rate <= 0:
            raise InvalidCostLine("fx_rate must be positive")
        usd, source = _money(amount_usd, "amount_usd").quantize(AMOUNT_QUANTUM), fx_source
    return CostLine(
        usage_date=usage_date,
        line_kind=line_kind,
        canonical_service=canonical_service,
        charge_class=charge_class,
        cost_bucket=cost_bucket,
        currency=currency,
        amount=amount_d,
        amount_usd=usd,
        dim_1=dim_1,
        dim_2=dim_2,
        line_key=line_key,
        fx_rate=rate,
        fx_source=source,
        is_estimated=is_estimated,
    )


# ── Pure aggregation ─────────────────────────────────────────────────────────────


def aggregate_contributions(contributions: Iterable[Contribution]) -> list[ShadowTotal]:
    """Sum authoritative, present records per (day, provider, bucket). Pure: no database access."""
    buckets: dict[tuple, dict[str, Any]] = defaultdict(
        lambda: {"total": Decimal(0), "counted": 0, "unconverted": 0, "blocked": 0, "estimated": 0, "known": False}
    )
    for c in contributions:
        b = buckets[(c.usage_date, c.provider, c.cost_bucket)]
        if not c.authoritative:
            continue
        if c.source_kind == "provider" and c.coverage_state in ("conflict", "suspect_empty"):
            b["blocked"] += 1
        if c.source_kind == "provider" and c.coverage_state == "estimated":
            b["estimated"] += 1
        if not c.present:
            continue
        b["counted"] += 1
        if c.amount_usd is None:
            b["unconverted"] += 1
        else:
            b["total"] += c.amount_usd
            b["known"] = True
    totals = []
    for (day, provider, bucket), b in sorted(buckets.items()):
        if b["unconverted"] or b["blocked"]:
            completeness = "incomplete"
        elif b["estimated"]:
            completeness = "estimated"
        else:
            completeness = "complete"
        known = b["known"] or (b["counted"] == 0 and not b["blocked"])
        amount = b["total"].quantize(CENT, rounding=ROUND_HALF_UP) if known else None
        totals.append(
            ShadowTotal(day, provider, bucket, amount, completeness, b["counted"], b["unconverted"], b["blocked"])
        )
    return totals


# ── Service ──────────────────────────────────────────────────────────────────────


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days)]


class CostLedgerService:
    def __init__(self, session: Session):
        self.db = session

    def _x(self, sql: str, **params: Any):
        return self.db.execute(text(sql), params)

    def _lock_team(self, team_id: UUID) -> None:
        self._x("SELECT pg_advisory_xact_lock(hashtextextended('heliox:cost-ledger:' || :t, 0))", t=str(team_id))

    # Streams and bindings

    def register_stream(self, identity: StreamIdentity) -> UUID:
        """Return the stream for this identity, creating it once (concurrency-safe)."""
        params = dict(
            id=uuid4(),
            team=identity.team_id,
            kind=identity.source_kind,
            role=identity.role,
            provider=identity.provider,
            scope=identity.scope_type,
            ba=identity.billing_account,
            ua=identity.usage_account,
            vantage=identity.vantage,
            metric=identity.metric,
            version=identity.grouping_version,
            sha=identity.config_sha256,
        )
        self._x(
            "INSERT INTO cost_source_streams (id, team_id, source_kind, role, provider, scope_type, billing_account, "
            "usage_account, vantage, metric, grouping_version, config_sha256) VALUES (:id, :team, :kind, :role, "
            ":provider, :scope, :ba, :ua, :vantage, :metric, :version, :sha) "
            "ON CONFLICT ON CONSTRAINT uq_cost_source_streams_identity DO NOTHING",
            **params,
        )
        return self._x(
            "SELECT id FROM cost_source_streams WHERE team_id = :team AND source_kind = :kind AND role = :role "
            "AND provider = :provider AND scope_type = :scope AND billing_account = :ba AND usage_account = :ua "
            "AND vantage = :vantage AND metric = :metric AND grouping_version = :version AND config_sha256 = :sha",
            **params,
        ).scalar_one()

    def bind_connection(self, stream_id: UUID, connection_id: UUID) -> None:
        """Bind a connection to a stream of the same team (the composite foreign key enforces the tenant)."""
        self._x(
            "INSERT INTO cost_source_stream_bindings (team_id, stream_id, connection_id) "
            "SELECT team_id, id, :c FROM cost_source_streams WHERE id = :s "
            "ON CONFLICT (stream_id, connection_id) DO UPDATE SET unbound_at = NULL",
            s=stream_id,
            c=connection_id,
        )

    # Runs and leases (minimal; scheduling and retries are a later step)

    def start_run(self, connection_id: UUID, *, billing_exempt: bool = False, triggered_by: str = "manual") -> UUID:
        run_id = uuid4()
        self._x(
            "INSERT INTO integration_sync_runs (id, connection_id, started_at, status, triggered_by, pipeline, phase, "
            "dispatch_deadline_at, billing_exempt) VALUES (:id, :c, now(), 'running', :by, 'ledger', 'queued', "
            "now() + interval '10 minutes', :exempt)",
            id=run_id,
            c=connection_id,
            by=triggered_by,
            exempt=billing_exempt,
        )
        return run_id

    def acquire_lease(self, run_id: UUID, attempt: int = 1) -> Optional[int]:
        """Take the connection's lease if free or expired; returns the new fencing token or None."""
        conn_id = self._x("SELECT connection_id FROM integration_sync_runs WHERE id = :r", r=run_id).scalar_one()
        self._x("INSERT INTO cost_sync_leases (connection_id) VALUES (:c) ON CONFLICT DO NOTHING", c=conn_id)
        token = self._x(
            "UPDATE cost_sync_leases SET token = token + 1, holder_run_id = :r, holder_attempt = :a, "
            "expires_at = clock_timestamp() + :ttl, heartbeat_at = clock_timestamp() "
            "WHERE connection_id = :c AND (holder_run_id IS NULL OR expires_at < clock_timestamp()) RETURNING token",
            r=run_id,
            a=attempt,
            c=conn_id,
            ttl=LEASE_TTL,
        ).scalar()
        if token is not None:
            self._x(
                "UPDATE integration_sync_runs SET phase = 'leased', attempt = :a, lease_token = :t, "
                "fetch_started_at = clock_timestamp(), heartbeat_at = clock_timestamp(), "
                "phase_changed_at = clock_timestamp() WHERE id = :r",
                a=attempt,
                t=token,
                r=run_id,
            )
        return token

    def finish_run(self, run_id: UUID, *, status: str = "success") -> None:
        self._x(
            "UPDATE integration_sync_runs SET phase = :p, status = :s, published_at = now(), finished_at = now() "
            "WHERE id = :r",
            p="published" if status == "success" else "failed",
            s=status,
            r=run_id,
        )
        self._x(
            "UPDATE cost_sync_leases SET holder_run_id = NULL, holder_attempt = NULL, expires_at = NULL "
            "WHERE holder_run_id = :r",
            r=run_id,
        )

    # Publication

    def publish(self, pub: Publication) -> PublishOutcome:
        out = PublishOutcome(fetched=len(pub.lines))
        days = _days(pub.window_start, pub.window_end)
        if not days:
            raise InvalidCostLine("empty publication window")
        seen = set()
        for line in pub.lines:
            if not pub.window_start <= line.usage_date < pub.window_end:
                raise InvalidCostLine("line outside the publication window")
            if line.identity in seen:
                raise InvalidCostLine("duplicate line identity in one publication")
            seen.add(line.identity)

        run = self._x(
            "SELECT r.connection_id, r.fetch_started_at, r.billing_exempt, c.team_id, l.holder_run_id, l.token, "
            "l.expires_at > clock_timestamp() AS live FROM integration_sync_runs r "
            "JOIN integration_connections c ON c.id = r.connection_id "
            "JOIN cost_sync_leases l ON l.connection_id = r.connection_id WHERE r.id = :r FOR UPDATE OF l",
            r=pub.run_id,
        ).one_or_none()
        if run is None or run.holder_run_id != pub.run_id or run.token != pub.fencing_token or not run.live:
            raise LedgerFenced("run does not hold the connection lease")
        stream = self._x("SELECT * FROM cost_source_streams WHERE id = :s", s=pub.stream_id).one_or_none()
        if stream is None or stream.team_id != run.team_id:
            raise TenantMismatch("stream does not belong to the connection's team")
        bound = self._x(
            "SELECT 1 FROM cost_source_stream_bindings WHERE stream_id = :s AND connection_id = :c AND unbound_at IS NULL",
            s=pub.stream_id,
            c=run.connection_id,
        ).scalar()
        if not bound:
            raise TenantMismatch("stream is not bound to the connection")
        self._lock_team(run.team_id)
        mode = self._x("SELECT ledger_mode FROM team_cost_ledger_settings WHERE team_id = :t", t=run.team_id).scalar()
        if mode in (None, "off"):
            raise LedgerDisabled("cost ledger is off for this team")
        if self._x(
            "SELECT 1 FROM cost_sync_run_streams WHERE sync_run_id = :r AND stream_id = :s AND status = 'published'",
            r=pub.run_id,
            s=pub.stream_id,
        ).scalar():
            raise AlreadyPublished("this run already published this stream")
        if not pub.complete:
            out.incomplete = True
            return out  # nothing written, coverage unchanged

        self._x(
            "INSERT INTO cost_sync_run_streams (sync_run_id, connection_id, attempt, team_id, stream_id, window_start, "
            "window_end, status, staged_rows) VALUES (:r, :c, :a, :t, :s, :ws, :we, 'published', :n)",
            r=pub.run_id,
            c=run.connection_id,
            a=pub.attempt,
            t=run.team_id,
            s=pub.stream_id,
            ws=pub.window_start,
            we=pub.window_end,
            n=len(pub.lines),
        )

        prior = {
            r.usage_date: r
            for r in self._x(
                "SELECT usage_date, generation, last_fetch_started_at FROM cost_source_stream_days "
                "WHERE stream_id = :s AND usage_date = ANY(:d)",
                s=pub.stream_id,
                d=days,
            )
        }
        active = [d for d in days if not (d in prior and prior[d].last_fetch_started_at > run.fetch_started_at)]
        out.stale = len(days) - len(active)
        gen = {d: (prior[d].generation + 1 if d in prior else 1) for d in active}
        existing = {
            (r.usage_date, r.dim_1, r.dim_2, r.line_kind, r.line_key, r.currency): r
            for r in self._x(
                "SELECT id, usage_date, dim_1, dim_2, line_kind, line_key, currency, amount, amount_usd, is_estimated, "
                "state FROM cost_source_records WHERE stream_id = :s AND usage_date = ANY(:d)",
                s=pub.stream_id,
                d=active,
            )
        }
        lines = [ln for ln in pub.lines if ln.usage_date in gen]
        with_lines = {ln.usage_date for ln in lines}
        suspect = {
            d
            for d in active
            if d not in with_lines
            and any(k[0] == d and r.state == "present" and r.amount != 0 for k, r in existing.items())
        }
        out.held = len(suspect)

        obs_base = dict(t=run.team_id, run=pub.run_id, c=run.connection_id, a=pub.attempt, tok=pub.fencing_token)
        for ln in lines:
            record_id = self._x(
                "INSERT INTO cost_source_records AS r (id, team_id, stream_id, source_kind, usage_date, dim_1, dim_2, "
                "line_kind, line_key, currency, canonical_service, charge_class, amount, amount_usd, fx_rate, fx_source, "
                "cost_bucket, is_estimated, state, last_generation) VALUES (:id, :t, :s, :kind, :d, :d1, :d2, :lk, :key, "
                ":cur, :svc, :cls, :amt, :usd, :fx, :fxs, :bucket, :est, 'present', :g) "
                "ON CONFLICT ON CONSTRAINT uq_cost_source_records_identity DO UPDATE SET amount = EXCLUDED.amount, "
                "amount_usd = EXCLUDED.amount_usd, fx_rate = EXCLUDED.fx_rate, fx_source = EXCLUDED.fx_source, "
                "is_estimated = EXCLUDED.is_estimated, canonical_service = EXCLUDED.canonical_service, "
                "charge_class = EXCLUDED.charge_class, cost_bucket = EXCLUDED.cost_bucket, state = 'present', "
                "absent_since_generation = NULL, absent_at = NULL, last_generation = EXCLUDED.last_generation, "
                "updated_at = now() RETURNING r.id",
                id=uuid4(),
                t=run.team_id,
                s=pub.stream_id,
                kind=stream.source_kind,
                d=ln.usage_date,
                d1=ln.dim_1,
                d2=ln.dim_2,
                lk=ln.line_kind,
                key=ln.line_key,
                cur=ln.currency,
                svc=ln.canonical_service,
                cls=ln.charge_class,
                amt=ln.amount,
                usd=ln.amount_usd,
                fx=ln.fx_rate,
                fxs=ln.fx_source,
                bucket=ln.cost_bucket,
                est=ln.is_estimated,
                g=gen[ln.usage_date],
            ).scalar_one()
            before = existing.get(ln.identity)
            if before is None:
                kind = "inserted"
            elif before.state == "absent":
                kind = "reappeared"
            elif (before.amount, before.amount_usd, before.is_estimated) != (ln.amount, ln.amount_usd, ln.is_estimated):
                kind = "corrected"
            else:
                kind = "unchanged"
            setattr(out, kind, getattr(out, kind) + 1)
            self._observe(
                record_id,
                kind,
                ln.amount,
                ln.currency,
                ln.amount_usd,
                before.amount if before else None,
                ln.is_estimated,
                gen[ln.usage_date],
                obs_base,
                repr(ln.identity) + str(ln.amount),
            )

        current = {ln.identity for ln in lines}
        for key, rec in existing.items():
            if rec.state != "present" or key in current or key[0] in suspect:
                continue
            self._x(
                "UPDATE cost_source_records SET state = 'absent', absent_since_generation = :g, absent_at = now(), "
                "last_generation = :g, updated_at = now() WHERE id = :id",
                g=gen[key[0]],
                id=rec.id,
            )
            self._observe(
                rec.id,
                "absent",
                None,
                rec.currency,
                None,
                rec.amount,
                rec.is_estimated,
                gen[key[0]],
                obs_base,
                f"absent:{rec.id}",
            )
            out.retired += 1

        for d in active:
            if d in suspect:
                state = "suspect_empty"
            elif any(ln.is_estimated for ln in lines if ln.usage_date == d):
                state = "estimated"
            else:
                state = "final"
            self._x(
                "INSERT INTO cost_source_stream_days AS sd (team_id, stream_id, usage_date, state, generation, "
                "last_fetch_started_at, last_run_id, last_connection_id, last_fencing_token, record_count, "
                "converted_total_usd, unconverted_count) SELECT :t, :s, :d, :st, :g, :f, :r, :c, :tok, count(*), "
                "coalesce(sum(amount_usd), 0), count(*) FILTER (WHERE amount_usd IS NULL) FROM cost_source_records "
                "WHERE stream_id = :s AND usage_date = :d AND state = 'present' "
                "ON CONFLICT (stream_id, usage_date) DO UPDATE SET state = EXCLUDED.state, "
                "generation = EXCLUDED.generation, last_fetch_started_at = EXCLUDED.last_fetch_started_at, "
                "last_run_id = EXCLUDED.last_run_id, last_connection_id = EXCLUDED.last_connection_id, "
                "last_fencing_token = EXCLUDED.last_fencing_token, record_count = EXCLUDED.record_count, "
                "converted_total_usd = EXCLUDED.converted_total_usd, unconverted_count = EXCLUDED.unconverted_count, "
                "updated_at = now()",
                t=run.team_id,
                s=pub.stream_id,
                d=d,
                st=state,
                g=gen[d],
                f=run.fetch_started_at,
                r=pub.run_id,
                c=run.connection_id,
                tok=pub.fencing_token,
            )
        out.published_days = active

        if stream.role == "attribution":
            self._reconcile_attribution(stream, active)
        else:
            out.quarantined = self._update_coverage(stream, active, pub.run_id)
            out.new_shadow_facts = self._register_facts(stream, active, pub.run_id, run.billing_exempt)

        legacy_qty = sum(1 for ln in lines if ln.amount != 0) if stream.role == "cost" else 0
        for basis, qty in (("first_ingested", out.new_shadow_facts), ("legacy_saved_rows", legacy_qty)):
            self._x(
                "INSERT INTO billing_usage_ledger (id, team_id, event_type, idempotency_key, basis, quantity, shadow, "
                "billing_exempt, sync_run_id, connection_id, stream_id, accrual_date) VALUES (:id, :t, 'ingestion', "
                ":k, :b, :q, true, :ex, :r, :c, :s, current_date) "
                "ON CONFLICT ON CONSTRAINT uq_billing_usage_ledger_key DO NOTHING",
                id=uuid4(),
                t=run.team_id,
                k=f"ingest:v2:{pub.run_id}:{pub.stream_id}",
                b=basis,
                q=qty,
                ex=run.billing_exempt,
                r=pub.run_id,
                c=run.connection_id,
                s=pub.stream_id,
            )
        logger.info(
            "cost ledger publish stream=%s fetched=%d inserted=%d corrected=%d unchanged=%d retired=%d held=%d "
            "stale=%d quarantined=%d",
            pub.stream_id,
            out.fetched,
            out.inserted,
            out.corrected,
            out.unchanged,
            out.retired,
            out.held,
            out.stale,
            out.quarantined,
        )
        return out

    def _observe(self, record_id, kind, amount, currency, amount_usd, previous, estimated, generation, base, payload):
        self._x(
            "INSERT INTO cost_source_observations (id, team_id, record_id, sync_run_id, connection_id, attempt, "
            "fencing_token, generation, change_kind, observed_amount, observed_currency, observed_amount_usd, "
            "previous_amount, is_estimated, payload_sha256) VALUES (:id, :t, :rec, :run, :c, :a, :tok, :g, :k, :amt, "
            ":cur, :usd, :prev, :est, :sha)",
            id=uuid4(),
            rec=record_id,
            g=generation,
            k=kind,
            amt=amount,
            cur=currency,
            usd=amount_usd,
            prev=previous,
            est=estimated,
            sha=hashlib.sha256(payload.encode()).digest(),
            **base,
        )

    def _update_coverage(self, stream, days: list[date], run_id: UUID) -> int:
        acct = dict(t=stream.team_id, p=stream.provider, ba=stream.billing_account, ua=stream.usage_account)
        configured = self._x(
            "SELECT stream_id FROM cost_source_authority WHERE team_id = :t AND provider = :p "
            "AND billing_account = :ba AND usage_account = :ua",
            **acct,
        ).scalar()
        opened = 0
        for d in days:
            authority = configured or stream.id
            if (
                authority != stream.id
                and not self._x(
                    "SELECT 1 FROM cost_source_stream_days WHERE stream_id = :a AND usage_date = :d", a=authority, d=d
                ).scalar()
            ):
                authority = None  # the configured authority has not published this day: this stream is a witness
            if authority is not None:
                self._x(
                    "INSERT INTO cost_source_coverage AS c (team_id, provider, billing_account, usage_account, usage_date, "
                    "authoritative_stream_id, state, authority_source, generation) SELECT :t, :p, :ba, :ua, :d, :auth, "
                    "sd.state, :src, 1 FROM cost_source_stream_days sd WHERE sd.stream_id = :auth AND sd.usage_date = :d "
                    "ON CONFLICT (team_id, provider, billing_account, usage_account, usage_date) DO UPDATE SET "
                    "state = CASE WHEN c.authoritative_stream_id = :s THEN EXCLUDED.state ELSE c.state END, "
                    "generation = c.generation + 1, updated_at = now()",
                    d=d,
                    auth=authority,
                    s=stream.id,
                    src="configured" if configured else "default_precedence",
                    **acct,
                )
            cov = self._x(
                "SELECT authoritative_stream_id FROM cost_source_coverage WHERE team_id = :t AND provider = :p "
                "AND billing_account = :ba AND usage_account = :ua AND usage_date = :d",
                d=d,
                **acct,
            ).scalar()
            if cov is None:
                continue
            opened += self._x(
                "INSERT INTO cost_source_conflicts (id, team_id, provider, billing_account, usage_account, usage_date, "
                "authoritative_stream_id, witness_stream_id, authoritative_total_usd, witness_total_usd, detected_run_id) "
                "SELECT gen_random_uuid(), :t, :p, :ba, :ua, :d, :auth, w.stream_id, a.converted_total_usd, "
                "w.converted_total_usd, :run FROM cost_source_stream_days a "
                "JOIN cost_source_streams ws ON ws.team_id = :t AND ws.provider = :p AND ws.billing_account = :ba "
                "AND ws.usage_account = :ua AND ws.role = 'cost' AND ws.id <> :auth "
                "JOIN cost_source_stream_days w ON w.stream_id = ws.id AND w.usage_date = :d "
                "WHERE a.stream_id = :auth AND a.usage_date = :d AND (a.unconverted_count > 0 OR w.unconverted_count > 0 "
                "OR abs(a.converted_total_usd - w.converted_total_usd) > :tol) "
                "ON CONFLICT (team_id, provider, billing_account, usage_account, usage_date, witness_stream_id) "
                "WHERE status = 'open' DO NOTHING",
                d=d,
                auth=cov,
                run=run_id,
                tol=WITNESS_TOLERANCE_USD,
                **acct,
            ).rowcount
            self._x(
                "UPDATE cost_source_coverage c SET state = 'conflict' WHERE team_id = :t AND provider = :p "
                "AND billing_account = :ba AND usage_account = :ua AND usage_date = :d AND EXISTS (SELECT 1 FROM "
                "cost_source_conflicts k WHERE k.status = 'open' AND k.team_id = c.team_id AND k.provider = c.provider "
                "AND k.billing_account = c.billing_account AND k.usage_account = c.usage_account "
                "AND k.usage_date = c.usage_date)",
                d=d,
                **acct,
            )
        return opened

    def _register_facts(self, stream, days: list[date], run_id: Optional[UUID], exempt: bool) -> int:
        """Record canonical facts of the authoritative records: always non-billable while shadow-only."""
        if not days:
            return 0
        return self._x(
            "INSERT INTO billing_canonical_facts (team_id, provider, billing_account, usage_account, usage_date, "
            "canonical_service, charge_class, currency, first_record_id, first_run_id, registered_in, first_billable) "
            "SELECT DISTINCT ON (r.usage_date, r.canonical_service, r.charge_class, r.currency) :t, :p, :ba, :ua, "
            "r.usage_date, r.canonical_service, r.charge_class, r.currency, r.id, :run, :reg, false "
            "FROM cost_source_records r JOIN cost_source_coverage c ON c.team_id = r.team_id AND c.provider = :p "
            "AND c.billing_account = :ba AND c.usage_account = :ua AND c.usage_date = r.usage_date "
            "AND c.authoritative_stream_id = r.stream_id "
            "WHERE r.team_id = :t AND r.state = 'present' AND r.charge_class <> 'other' AND r.usage_date = ANY(:d) "
            "ORDER BY r.usage_date, r.canonical_service, r.charge_class, r.currency, r.id "
            "ON CONFLICT DO NOTHING",
            t=stream.team_id,
            p=stream.provider,
            ba=stream.billing_account,
            ua=stream.usage_account,
            run=run_id,
            reg="backfill" if exempt else "shadow",
            d=days,
        ).rowcount

    def _reconcile_attribution(self, stream, days: list[date]) -> None:
        for d in days:
            auth = self._x(
                "SELECT authoritative_stream_id FROM cost_source_coverage WHERE team_id = :t AND provider = :p "
                "AND billing_account = :ba AND usage_account = :ua AND usage_date = :d",
                t=stream.team_id,
                p=stream.provider,
                ba=stream.billing_account,
                ua=stream.usage_account,
                d=d,
            ).scalar()
            if auth is None:
                status = "no_cost_coverage"
            else:
                mismatch = self._x(
                    "SELECT 1 FROM (SELECT canonical_service, sum(amount_usd) AS amt FROM cost_source_records "
                    "WHERE stream_id = :s AND usage_date = :d AND state = 'present' GROUP BY 1) a FULL JOIN "
                    "(SELECT canonical_service, sum(amount_usd) AS amt FROM cost_source_records WHERE stream_id = :auth "
                    "AND usage_date = :d AND state = 'present' GROUP BY 1) k USING (canonical_service) "
                    "WHERE a.amt IS DISTINCT FROM k.amt LIMIT 1",
                    s=stream.id,
                    auth=auth,
                    d=d,
                ).scalar()
                status = "mismatch" if mismatch else "reconciled"
            self._x(
                "UPDATE cost_source_stream_days SET attribution_status = :st WHERE stream_id = :s AND usage_date = :d",
                st=status,
                s=stream.id,
                d=d,
            )

    # Authority and conflicts (explicit and audited; never automatic)

    def set_authority(
        self,
        *,
        team_id: UUID,
        provider: str,
        billing_account: str,
        usage_account: str,
        stream_id: UUID,
        actor_user_id: UUID,
        reason: str,
    ) -> int:
        """Make a cost stream authoritative for an account. Returns newly registered (non-billable) facts."""
        if not reason:
            raise LedgerError("an authority change needs a reason")
        self._lock_team(team_id)
        acct = dict(t=team_id, p=provider, ba=billing_account, ua=usage_account)
        previous = self._x(
            "SELECT stream_id FROM cost_source_authority WHERE team_id = :t AND provider = :p "
            "AND billing_account = :ba AND usage_account = :ua",
            **acct,
        ).scalar()
        self._x(
            "INSERT INTO cost_source_authority (team_id, provider, billing_account, usage_account, stream_id, set_by, "
            "reason) VALUES (:t, :p, :ba, :ua, :s, :u, :why) ON CONFLICT (team_id, provider, billing_account, "
            "usage_account) DO UPDATE SET stream_id = EXCLUDED.stream_id, set_by = EXCLUDED.set_by, set_at = now(), "
            "reason = EXCLUDED.reason",
            s=stream_id,
            u=actor_user_id,
            why=reason,
            **acct,
        )
        self._x(
            "INSERT INTO cost_source_authority_history (id, team_id, provider, billing_account, usage_account, "
            "from_stream_id, to_stream_id, changed_by, reason) VALUES (:id, :t, :p, :ba, :ua, :f, :s, :u, :why)",
            id=uuid4(),
            f=previous,
            s=stream_id,
            u=actor_user_id,
            why=reason,
            **acct,
        )
        moved = [
            r.usage_date
            for r in self._x(
                "UPDATE cost_source_coverage c SET authoritative_stream_id = :s, state = sd.state, "
                "authority_source = 'reviewed', generation = c.generation + 1, updated_at = now() "
                "FROM cost_source_stream_days sd WHERE c.team_id = :t AND c.provider = :p AND c.billing_account = :ba "
                "AND c.usage_account = :ua AND sd.stream_id = :s AND sd.usage_date = c.usage_date RETURNING c.usage_date",
                s=stream_id,
                **acct,
            )
        ]
        stream = self._x("SELECT * FROM cost_source_streams WHERE id = :s", s=stream_id).one()
        return self._register_facts(stream, moved, None, False)

    def resolve_conflict(self, conflict_id: UUID, *, actor_user_id: UUID, reason: str) -> None:
        """Keep the authoritative value for a quarantined conflict (audited)."""
        row = self._x(
            "UPDATE cost_source_conflicts SET status = 'resolved_keep_authoritative', resolved_by = :u, "
            "resolved_at = now(), resolution_reason = :why WHERE id = :id AND status = 'open' "
            "RETURNING team_id, provider, billing_account, usage_account, usage_date",
            u=actor_user_id,
            why=reason,
            id=conflict_id,
        ).one_or_none()
        if row is None:
            raise LedgerError("no open conflict with this id")
        self._x(
            "UPDATE cost_source_coverage c SET state = sd.state, generation = c.generation + 1 "
            "FROM cost_source_stream_days sd WHERE c.team_id = :t AND c.provider = :p AND c.billing_account = :ba "
            "AND c.usage_account = :ua AND c.usage_date = :d AND sd.stream_id = c.authoritative_stream_id "
            "AND sd.usage_date = c.usage_date AND NOT EXISTS (SELECT 1 FROM cost_source_conflicts k "
            "WHERE k.status = 'open' AND k.team_id = c.team_id AND k.provider = c.provider "
            "AND k.billing_account = c.billing_account AND k.usage_account = c.usage_account "
            "AND k.usage_date = c.usage_date)",
            t=row.team_id,
            p=row.provider,
            ba=row.billing_account,
            ua=row.usage_account,
            d=row.usage_date,
        )

    # Shadow totals (read-only)

    def shadow_totals(self, team_id: UUID, days: Sequence[date]) -> list[ShadowTotal]:
        rows = self._x(
            "SELECT r.usage_date, s.provider, r.cost_bucket, r.amount_usd, r.state = 'present' AS present, "
            "s.source_kind, c.state AS coverage_state, (s.source_kind = 'manual' OR (s.role = 'cost' "
            "AND c.authoritative_stream_id = r.stream_id)) AS authoritative FROM cost_source_records r "
            "JOIN cost_source_streams s ON s.team_id = r.team_id AND s.id = r.stream_id "
            "LEFT JOIN cost_source_coverage c ON c.team_id = r.team_id AND c.provider = s.provider "
            "AND c.billing_account = s.billing_account AND c.usage_account = s.usage_account "
            "AND c.usage_date = r.usage_date WHERE r.team_id = :t AND r.usage_date = ANY(:d)",
            t=team_id,
            d=list(days),
        )
        return aggregate_contributions(
            Contribution(
                r.usage_date,
                r.provider,
                r.cost_bucket,
                r.amount_usd,
                r.present,
                bool(r.authoritative),
                r.source_kind,
                r.coverage_state,
            )
            for r in rows
        )
