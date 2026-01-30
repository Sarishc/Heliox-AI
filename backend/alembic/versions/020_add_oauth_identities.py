"""add oauth identities

Revision ID: 020
Revises: 019
Create Date: 2026-01-30 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create OAuth provider enum
    op.execute("""
        CREATE TYPE oauthprovider AS ENUM (
            'google',
            'github',
            'microsoft',
            'okta'
        )
    """)
    
    # Create oauth_identities table
    op.create_table(
        'oauth_identities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_user_id', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('picture', sa.String(512), nullable=True),
        sa.Column('access_token_encrypted', sa.String(512), nullable=True),
        sa.Column('refresh_token_encrypted', sa.String(512), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_oauth_identities_team_id', 'oauth_identities', ['team_id'])
    op.create_index('ix_oauth_identities_user_id', 'oauth_identities', ['user_id'])
    op.create_index('ix_oauth_identities_provider', 'oauth_identities', ['provider'])
    op.create_index('ix_oauth_identities_provider_user_id', 'oauth_identities', ['provider_user_id'])
    op.create_index('ix_oauth_identities_email', 'oauth_identities', ['email'])
    op.create_index('ix_oauth_identities_last_login_at', 'oauth_identities', ['last_login_at'])
    op.create_index('ix_oauth_identities_team_provider', 'oauth_identities', ['team_id', 'provider'])
    op.create_index('ix_oauth_identities_user_provider', 'oauth_identities', ['user_id', 'provider'])
    op.create_index('uq_oauth_provider_user', 'oauth_identities', ['provider', 'provider_user_id'], unique=True)
    
    # Add allowed_email_domains to teams table
    op.add_column('teams', sa.Column('allowed_email_domains', postgresql.ARRAY(sa.String(255)), nullable=True))
    op.add_column('teams', sa.Column('sso_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('teams', sa.Column('sso_enforce_domain', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove team SSO columns
    op.drop_column('teams', 'sso_enforce_domain')
    op.drop_column('teams', 'sso_enabled')
    op.drop_column('teams', 'allowed_email_domains')
    
    # Drop indexes
    op.drop_index('uq_oauth_provider_user', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_user_provider', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_team_provider', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_last_login_at', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_email', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_provider_user_id', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_provider', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_user_id', table_name='oauth_identities')
    op.drop_index('ix_oauth_identities_team_id', table_name='oauth_identities')
    
    # Drop table
    op.drop_table('oauth_identities')
    
    # Drop enum
    op.execute('DROP TYPE oauthprovider')
