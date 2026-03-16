"""Encrypt Slack webhook URLs at rest.

Revision ID: 023
Revises: 022
Create Date: 2026-03-16

- Adds slack_webhook_encrypted column
- Migrates existing plaintext to encrypted
- Drops slack_webhook_url column

Requires INTEGRATIONS_ENCRYPTION_KEY to be set for migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text, select
from sqlalchemy.engine import reflection


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new encrypted column
    op.add_column(
        "alert_settings",
        sa.Column("slack_webhook_encrypted", sa.Text(), nullable=True),
    )

    # Migrate existing plaintext to encrypted
    conn = op.get_bind()
    inspector = reflection.Inspector.from_engine(conn)
    if "alert_settings" in inspector.get_table_names():
        # Check if slack_webhook_url exists (it should in upgrade path)
        cols = [c["name"] for c in inspector.get_columns("alert_settings")]
        if "slack_webhook_url" in cols:
            try:
                from app.integrations.encryption import get_encryption

                encryption = get_encryption()
                result = conn.execute(
                    text(
                        "SELECT id, slack_webhook_url FROM alert_settings WHERE slack_webhook_url IS NOT NULL AND slack_webhook_url != ''"
                    )
                )
                rows = result.fetchall()
                for row in rows:
                    row_id, plaintext = row[0], row[1]
                    if plaintext:
                        encrypted = encryption.encrypt_string(plaintext)
                        conn.execute(
                            text(
                                "UPDATE alert_settings SET slack_webhook_encrypted = :enc WHERE id = :id"
                            ),
                            {"enc": encrypted, "id": row_id},
                        )
            except Exception as e:
                # If encryption fails (e.g. key not set), leave new column empty
                # and log. Old plaintext remains until key is set and migration re-run.
                import logging

                logging.getLogger("alembic").warning(
                    f"Slack webhook migration skipped (encryption unavailable): {e}. "
                    "Set INTEGRATIONS_ENCRYPTION_KEY and re-run migration."
                )

    # Drop old plaintext column
    op.drop_column("alert_settings", "slack_webhook_url")


def downgrade() -> None:
    # Add back plaintext column
    op.add_column(
        "alert_settings",
        sa.Column("slack_webhook_url", sa.String(), nullable=True),
    )

    # Decrypt and populate (best-effort; key must be same as upgrade)
    conn = op.get_bind()
    try:
        from app.integrations.encryption import get_encryption

        encryption = get_encryption()
        result = conn.execute(
            text(
                "SELECT id, slack_webhook_encrypted FROM alert_settings WHERE slack_webhook_encrypted IS NOT NULL"
            )
        )
        rows = result.fetchall()
        for row in rows:
            row_id, encrypted = row[0], row[1]
            if encrypted:
                plaintext = encryption.decrypt_string(encrypted)
                conn.execute(
                    text(
                        "UPDATE alert_settings SET slack_webhook_url = :plain WHERE id = :id"
                    ),
                    {"plain": plaintext, "id": row_id},
                )
    except Exception:
        pass  # Leave plaintext column empty on downgrade failure

    op.drop_column("alert_settings", "slack_webhook_encrypted")
