"""add stripe billing

Revision ID: 019
Revises: 018
Create Date: 2026-01-30 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subscription status enum
    op.execute("""
        CREATE TYPE subscriptionstatus AS ENUM (
            'active',
            'trialing',
            'past_due',
            'canceled',
            'unpaid',
            'incomplete',
            'incomplete_expired'
        )
    """)
    
    # Create billing plan enum
    op.execute("""
        CREATE TYPE billingplan AS ENUM (
            'free',
            'starter',
            'growth',
            'enterprise'
        )
    """)
    
    # Create team_subscriptions table
    op.create_table(
        'team_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stripe_customer_id', sa.String(255), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('plan', sa.String(50), nullable=False, server_default='free'),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trial_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('trial_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id'),
        sa.UniqueConstraint('stripe_customer_id'),
        sa.UniqueConstraint('stripe_subscription_id')
    )
    
    # Create indexes for team_subscriptions
    op.create_index('ix_team_subscriptions_team_id', 'team_subscriptions', ['team_id'])
    op.create_index('ix_team_subscriptions_status', 'team_subscriptions', ['status'])
    op.create_index('ix_team_subscriptions_plan', 'team_subscriptions', ['plan'])
    op.create_index('ix_team_subscriptions_stripe_customer', 'team_subscriptions', ['stripe_customer_id'])
    op.create_index('ix_team_subscriptions_stripe_subscription', 'team_subscriptions', ['stripe_subscription_id'])
    op.create_index('ix_team_subscriptions_current_period_end', 'team_subscriptions', ['current_period_end'])
    
    # Create team_entitlements table
    op.create_table(
        'team_entitlements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan', sa.String(50), nullable=False, server_default='free'),
        sa.Column('limits', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id')
    )
    
    # Create indexes for team_entitlements
    op.create_index('ix_team_entitlements_team_id', 'team_entitlements', ['team_id'])
    op.create_index('ix_team_entitlements_plan', 'team_entitlements', ['plan'])


def downgrade() -> None:
    # Drop tables
    op.drop_index('ix_team_entitlements_plan', table_name='team_entitlements')
    op.drop_index('ix_team_entitlements_team_id', table_name='team_entitlements')
    op.drop_table('team_entitlements')
    
    op.drop_index('ix_team_subscriptions_current_period_end', table_name='team_subscriptions')
    op.drop_index('ix_team_subscriptions_stripe_subscription', table_name='team_subscriptions')
    op.drop_index('ix_team_subscriptions_stripe_customer', table_name='team_subscriptions')
    op.drop_index('ix_team_subscriptions_plan', table_name='team_subscriptions')
    op.drop_index('ix_team_subscriptions_status', table_name='team_subscriptions')
    op.drop_index('ix_team_subscriptions_team_id', table_name='team_subscriptions')
    op.drop_table('team_subscriptions')
    
    # Drop enums
    op.execute('DROP TYPE billingplan')
    op.execute('DROP TYPE subscriptionstatus')
