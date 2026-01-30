"""add integrations

Revision ID: 016
Revises: 015
Create Date: 2026-01-27 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create integration_connections table
    op.create_table(
        'integration_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.Enum(
            'aws', 'gcp', 'azure', 'stripe', 'sso_google', 'sso_okta', 'slack', 'custom',
            name='integrationprovider'
        ), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config_encrypted', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum(
            'active', 'error', 'disabled', 'pending',
            name='integrationstatus'
        ), nullable=False, server_default='pending'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_successful_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sync_interval_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for integration_connections
    op.create_index('ix_integration_connections_team_id', 'integration_connections', ['team_id'])
    op.create_index('ix_integration_connections_provider', 'integration_connections', ['provider'])
    op.create_index('ix_integration_connections_status', 'integration_connections', ['status'])
    
    # Create integration_sync_runs table
    op.create_table(
        'integration_sync_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Enum(
            'running', 'success', 'failed', 'partial',
            name='syncstatus'
        ), nullable=False, server_default='running'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('error_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('metrics_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('triggered_by', sa.String(50), nullable=False, server_default='manual'),
        sa.ForeignKeyConstraint(['connection_id'], ['integration_connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for integration_sync_runs
    op.create_index('ix_integration_sync_runs_connection_id', 'integration_sync_runs', ['connection_id'])
    op.create_index('ix_integration_sync_runs_started_at', 'integration_sync_runs', ['started_at'])
    op.create_index('ix_integration_sync_runs_status', 'integration_sync_runs', ['status'])


def downgrade() -> None:
    # Drop tables
    op.drop_index('ix_integration_sync_runs_status', table_name='integration_sync_runs')
    op.drop_index('ix_integration_sync_runs_started_at', table_name='integration_sync_runs')
    op.drop_index('ix_integration_sync_runs_connection_id', table_name='integration_sync_runs')
    op.drop_table('integration_sync_runs')
    
    op.drop_index('ix_integration_connections_status', table_name='integration_connections')
    op.drop_index('ix_integration_connections_provider', table_name='integration_connections')
    op.drop_index('ix_integration_connections_team_id', table_name='integration_connections')
    op.drop_table('integration_connections')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS syncstatus')
    op.execute('DROP TYPE IF EXISTS integrationstatus')
    op.execute('DROP TYPE IF EXISTS integrationprovider')
