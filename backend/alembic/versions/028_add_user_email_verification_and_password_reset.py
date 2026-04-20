"""Add email verification and password reset fields to users table.

Revision ID: 028
Revises: 027
Create Date: 2026-03-23

- users.email_verified: bool, default False (regular signup must verify; OAuth users already trusted)
- users.email_verification_token: sha256 hex token, nullable
- users.password_reset_token: sha256 hex token, nullable
- users.password_reset_token_expires_at: expiry timestamp, nullable
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether the user has verified their email address",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verification_token",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex token for email verification (stored hashed)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_reset_token",
            sa.String(length=64),
            nullable=True,
            comment="SHA-256 hex token for password reset (stored hashed)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "password_reset_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Expiry timestamp for password reset token",
        ),
    )

    # Index for fast token lookups — used on every reset/verify request
    op.create_index(
        "ix_users_email_verification_token",
        "users",
        ["email_verification_token"],
        unique=True,
        postgresql_where=sa.text("email_verification_token IS NOT NULL"),
    )
    op.create_index(
        "ix_users_password_reset_token",
        "users",
        ["password_reset_token"],
        unique=True,
        postgresql_where=sa.text("password_reset_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_password_reset_token", table_name="users")
    op.drop_index("ix_users_email_verification_token", table_name="users")
    op.drop_column("users", "password_reset_token_expires_at")
    op.drop_column("users", "password_reset_token")
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "email_verified")
