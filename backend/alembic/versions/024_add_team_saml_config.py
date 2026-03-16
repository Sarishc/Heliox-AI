"""Add team_saml_config for SAML/Okta SSO.

Revision ID: 024
Revises: 023
Create Date: 2026-04-01

- team_saml_config: IdP metadata for team-scoped SAML SSO
- Enables Okta and other SAML 2.0 IdPs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_saml_config",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idp_entity_id", sa.String(512), nullable=False),
        sa.Column("idp_sso_url", sa.String(1024), nullable=False),
        sa.Column("idp_x509_cert", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("default_role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", name="uq_team_saml_config_team_id"),
    )
    op.create_index("ix_team_saml_config_team_id", "team_saml_config", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_team_saml_config_team_id", table_name="team_saml_config")
    op.drop_table("team_saml_config")
