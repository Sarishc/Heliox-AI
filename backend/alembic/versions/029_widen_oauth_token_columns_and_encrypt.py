"""Widen oauth token columns to Text and encrypt any plaintext rows.

Revision ID: 029
Revises: 028
Create Date: 2026-04-20 00:00:00.000000

Two changes in one migration so they deploy atomically:
  1. ALTER both token columns from VARCHAR(512) → TEXT so Fernet-encrypted
     tokens (which grow ~33 % over plaintext) never hit a truncation error.
  2. Encrypt any existing plaintext rows using INTEGRATIONS_ENCRYPTION_KEY.
     The encryption step is idempotent: rows that are already Fernet-encrypted
     are detected and skipped.

If INTEGRATIONS_ENCRYPTION_KEY is not set at migration time the column widening
still runs, but the encryption step is skipped with a warning.  Set the key and
re-run `alembic upgrade head` (or run the standalone script) to encrypt later.
"""
import base64
import logging
import os

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None

_TOKEN_COLUMNS = ("access_token_encrypted", "refresh_token_encrypted")


def _is_fernet_token(value: str) -> bool:
    """Return True if value appears to already be Fernet-encrypted."""
    if not value or len(value) < 56:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode() + b"==")
        return len(decoded) >= 41 and decoded[0] == 0x80
    except Exception:
        return False


def upgrade() -> None:
    # ── 1. Widen columns ──────────────────────────────────────────────────────
    for col in _TOKEN_COLUMNS:
        op.alter_column(
            "oauth_identities",
            col,
            type_=sa.Text(),
            existing_type=sa.String(512),
            existing_nullable=True,
        )

    # ── 2. Encrypt existing plaintext rows ────────────────────────────────────
    raw_key = os.environ.get("INTEGRATIONS_ENCRYPTION_KEY", "").strip()
    if not raw_key:
        logger.warning(
            "migration 029: INTEGRATIONS_ENCRYPTION_KEY is not set — "
            "skipping encryption of existing rows. "
            "Set the key and re-run `alembic upgrade head` to encrypt them."
        )
        return

    try:
        fernet = Fernet(raw_key.encode())
    except Exception as exc:
        raise RuntimeError(
            f"migration 029: INTEGRATIONS_ENCRYPTION_KEY is not a valid Fernet key: {exc}"
        ) from exc

    conn = op.get_bind()

    rows = conn.execute(
        sa.text(
            "SELECT id, access_token_encrypted, refresh_token_encrypted "
            "FROM oauth_identities "
            "WHERE access_token_encrypted IS NOT NULL "
            "   OR refresh_token_encrypted IS NOT NULL"
        )
    ).fetchall()

    encrypted_count = skipped_count = 0

    for row in rows:
        updates: dict = {}
        for col in _TOKEN_COLUMNS:
            value = getattr(row, col)
            if not value:
                continue
            if _is_fernet_token(value):
                skipped_count += 1
                continue
            # Plaintext row — encrypt it
            try:
                updates[col] = fernet.encrypt(value.encode()).decode()
            except Exception as exc:
                logger.error(
                    f"migration 029: failed to encrypt {col} for row {row.id}: {exc}"
                )

        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            conn.execute(
                sa.text(
                    f"UPDATE oauth_identities SET {set_clause} WHERE id = :id"
                ),
                {**updates, "id": str(row.id)},
            )
            encrypted_count += 1

    logger.info(
        f"migration 029: encrypted {encrypted_count} rows, "
        f"skipped {skipped_count} already-encrypted tokens."
    )


def downgrade() -> None:
    # Narrow columns back to VARCHAR(512).
    # NOTE: if any stored encrypted value is longer than 512 chars this will
    # fail.  Decrypt all tokens before downgrading in that case.
    for col in _TOKEN_COLUMNS:
        op.alter_column(
            "oauth_identities",
            col,
            type_=sa.String(512),
            existing_type=sa.Text(),
            existing_nullable=True,
        )
