"""The gates a connection must pass before any shadow ingestion may run."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings

REQUIRED_GATES = (
    "ck_batches_gate_no_apply",
    "ck_cost_snapshots_gate_legacy_only",
    "ck_facts_gate_not_billable",
    "ck_ledger_settings_gate_legacy_billing",
    "ck_ledger_settings_gate_no_live",
    "ck_usage_ledger_gate_shadow_only",
)
PERMITTED_ENVS = frozenset({"dev", "staging"})


class ShadowActivationRefused(Exception):
    """A required gate is closed. ``code`` is stable and free of secrets."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ShadowPolicy:
    """The environment-level part of activation. The flag alone activates nothing, least of all billing."""

    enabled: bool
    env: str

    @classmethod
    def from_settings(cls) -> "ShadowPolicy":
        settings = get_settings()
        return cls(enabled=settings.LEDGER_SHADOW_WORKER_ENABLED, env=settings.ENV)

    def require(self) -> None:
        if not self.enabled:
            raise ShadowActivationRefused("worker_disabled")
        if self.env not in PERMITTED_ENVS:
            raise ShadowActivationRefused("environment_not_permitted")


def verify_ledger_schema(session: Session) -> None:
    """Every shadow-only database gate must exist: this worker relies on them, not only on its own code."""
    present = set(
        session.execute(
            text("SELECT conname FROM pg_constraint WHERE conname = ANY(:names)"), {"names": list(REQUIRED_GATES)}
        ).scalars()
    )
    if present != set(REQUIRED_GATES):
        raise ShadowActivationRefused("ledger_schema_invalid")


def require_shadow_team(session: Session, team_id: UUID) -> None:
    mode = session.execute(
        text("SELECT ledger_mode FROM team_cost_ledger_settings WHERE team_id = :t"), {"t": team_id}
    ).scalar()
    if mode != "shadow":
        raise ShadowActivationRefused("team_not_in_shadow_mode")
