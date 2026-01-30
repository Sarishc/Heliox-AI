"""add usage metering

Revision ID: 018
Revises: 017
Create Date: 2026-01-30 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create usage event type enum
    op.execute("""
        CREATE TYPE usageeventtype AS ENUM (
            'api_request',
            'ingestion',
            'seat',
            'gpu_node'
        )
    """)
    
    # Create usage_events table
    op.create_table(
        'usage_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for usage_events
    op.create_index('ix_usage_events_team_id', 'usage_events', ['team_id'])
    op.create_index('ix_usage_events_event_type', 'usage_events', ['event_type'])
    op.create_index('ix_usage_events_team_created', 'usage_events', ['team_id', 'created_at'])
    op.create_index('ix_usage_events_team_type_created', 'usage_events', ['team_id', 'event_type', 'created_at'])
    op.create_index('ix_usage_events_created_at', 'usage_events', ['created_at'])
    
    # Create usage_daily_rollups table
    op.create_table(
        'usage_daily_rollups',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('total_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for usage_daily_rollups
    op.create_index('ix_usage_daily_rollups_team_id', 'usage_daily_rollups', ['team_id'])
    op.create_index('ix_usage_daily_rollups_event_type', 'usage_daily_rollups', ['event_type'])
    op.create_index('ix_usage_daily_rollups_date', 'usage_daily_rollups', ['date'])
    op.create_index(
        'ix_usage_daily_rollups_team_date_type',
        'usage_daily_rollups',
        ['team_id', 'date', 'event_type'],
        unique=True
    )


def downgrade() -> None:
    # Drop tables
    op.drop_index('ix_usage_daily_rollups_team_date_type', table_name='usage_daily_rollups')
    op.drop_index('ix_usage_daily_rollups_date', table_name='usage_daily_rollups')
    op.drop_index('ix_usage_daily_rollups_event_type', table_name='usage_daily_rollups')
    op.drop_index('ix_usage_daily_rollups_team_id', table_name='usage_daily_rollups')
    op.drop_table('usage_daily_rollups')
    
    op.drop_index('ix_usage_events_created_at', table_name='usage_events')
    op.drop_index('ix_usage_events_team_type_created', table_name='usage_events')
    op.drop_index('ix_usage_events_team_created', table_name='usage_events')
    op.drop_index('ix_usage_events_event_type', table_name='usage_events')
    op.drop_index('ix_usage_events_team_id', table_name='usage_events')
    op.drop_table('usage_events')
    
    # Drop enum
    op.execute('DROP TYPE usageeventtype')
