"""Add team_api_keys table

Revision ID: 005
Revises: 004
Create Date: 2026-01-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create team_api_keys table
    op.create_table(
        'team_api_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('team_id', sa.String(), nullable=False),
        sa.Column('key_name', sa.String(length=255), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_team_api_keys_team_id', 'team_api_keys', ['team_id'])
    op.create_index('ix_team_api_keys_key_hash', 'team_api_keys', ['key_hash'], unique=True)
    
    # Add foreign key
    op.create_foreign_key(
        'fk_team_api_keys_team_id',
        'team_api_keys',
        'teams',
        ['team_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    op.drop_index('ix_team_api_keys_key_hash', table_name='team_api_keys')
    op.drop_index('ix_team_api_keys_team_id', table_name='team_api_keys')
    op.drop_table('team_api_keys')
