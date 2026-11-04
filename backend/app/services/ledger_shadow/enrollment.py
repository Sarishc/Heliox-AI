"""
Private, audited enrollment of a connection's expected inventory. No API route calls this.

The caller verifies scope with the adapter first, with no transaction open, and passes the verdicts in;
it also commits. An operator decides to enroll: nothing enrolls a team or a connection automatically.
"""

from __future__ import annotations

from typing import Mapping, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.ledger.base import ScopeVerdict, StreamSpec
from app.models.audit_log import AuditLog
from app.services.ledger_shadow.activation import (
    ShadowActivationRefused,
    require_eligible_connection,
    require_shadow_team,
    verify_ledger_schema,
)
from app.services.ledger_shadow.inventory import AMBIGUOUS_SOURCE, ambiguous_streams, configure_inventory

ADMIN_ROLES = ("owner", "admin")


class EnrollmentRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def enroll_connection(
    session: Session,
    *,
    team_id: UUID,
    connection_id: UUID,
    actor_user_id: UUID,
    specs: Sequence[StreamSpec],
    verdicts: Mapping[str, ScopeVerdict],
    reason: str,
) -> list[UUID]:
    """Bind the verified inventory. Any refusal raises before a write; the caller rolls back in any case."""
    _common_checks(session, team_id, actor_user_id, reason)
    try:
        verify_ledger_schema(session)
        require_shadow_team(session, team_id)
        require_eligible_connection(session, connection_id, team_id)
    except ShadowActivationRefused as closed:
        raise EnrollmentRefused(closed.code) from None
    if not specs:
        raise EnrollmentRefused("inventory_empty")
    unverified = sorted(
        s.usage_account for s in specs if not verdicts.get(s.usage_account, ScopeVerdict(False)).verified
    )
    if unverified:
        raise EnrollmentRefused("scope_unverified")
    _refuse_during_a_run(session, connection_id)
    stream_ids = configure_inventory(session, team_id, connection_id, specs)
    if ambiguous_streams(session, stream_ids):
        raise EnrollmentRefused(AMBIGUOUS_SOURCE)  # the caller's rollback undoes the bindings above
    _audit(
        session,
        team_id,
        actor_user_id,
        "cost_ledger.inventory_enrolled",
        {"connection_id": str(connection_id), "accounts": sorted(s.usage_account for s in specs), "reason": reason},
    )
    return stream_ids


def revoke_connection(session: Session, *, team_id: UUID, connection_id: UUID, actor_user_id: UUID, reason: str) -> int:
    """Stop expecting anything from this connection. History stays; an in-flight run is refused when it next checks."""
    _common_checks(session, team_id, actor_user_id, reason)
    owner = session.execute(
        text("SELECT team_id FROM integration_connections WHERE id = :c"), {"c": connection_id}
    ).scalar()
    if owner != team_id:
        raise EnrollmentRefused("connection_not_owned")
    revoked = session.execute(
        text(
            "UPDATE cost_source_stream_bindings SET unbound_at = now() WHERE connection_id = :c AND team_id = :t "
            "AND unbound_at IS NULL RETURNING stream_id"
        ),
        {"c": connection_id, "t": team_id},
    ).all()
    _audit(
        session,
        team_id,
        actor_user_id,
        "cost_ledger.inventory_revoked",
        {"connection_id": str(connection_id), "streams": len(revoked), "reason": reason},
    )
    return len(revoked)


def _common_checks(session: Session, team_id: UUID, actor_user_id: UUID, reason: str) -> None:
    if not reason or not reason.strip():
        raise EnrollmentRefused("reason_required")
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended('heliox:cost-ledger:' || :t, 0))"), {"t": str(team_id)}
    )
    role = session.execute(
        text("SELECT role FROM team_members WHERE team_id = :t AND user_id = :u"), {"t": team_id, "u": actor_user_id}
    ).scalar()
    if str(role) not in ADMIN_ROLES:
        raise EnrollmentRefused("actor_not_authorized")


def _refuse_during_a_run(session: Session, connection_id: UUID) -> None:
    running = session.execute(
        text(
            "SELECT 1 FROM integration_sync_runs WHERE connection_id = :c AND pipeline = 'ledger' "
            "AND phase IN ('queued', 'leased', 'fetching', 'publishing')"
        ),
        {"c": connection_id},
    ).scalar()
    if running:
        raise EnrollmentRefused("run_in_flight")


def _audit(session: Session, team_id: UUID, actor_user_id: UUID, action: str, metadata: dict) -> None:
    session.add(
        AuditLog(
            team_id=team_id, actor_type="user", actor_id=str(actor_user_id), action=action, event_metadata=metadata
        )
    )
