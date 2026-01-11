"""Add alert settings table

Revision ID: 003
Revises: 002
Create Date: 2026-01-09 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create alert_settings table
    op.create_table(
        'alert_settings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('team_id', sa.String(), nullable=False),
        sa.Column('burn_rate_threshold_usd_per_day', sa.Numeric(10, 2), nullable=False, server_default='10000.00'),
        sa.Column('enable_slack', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('enable_email', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_recipients', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_alert_settings_team_id', 'alert_settings', ['team_id'], unique=True)
    
    # Add foreign key
    op.create_foreign_key(
        'fk_alert_settings_team_id',
        'alert_settings',
        'teams',
        ['team_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    op.drop_table('alert_settings')
