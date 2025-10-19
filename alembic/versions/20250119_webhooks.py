"""add webhooks tables

Revision ID: 20250119_webhooks
Revises: 20250119_files_parser_runs
Create Date: 2025-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250119_webhooks'
down_revision = '20250119_files_parser_runs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create webhooks and webhook_deliveries tables."""
    
    # Create webhooks table
    op.create_table(
        'webhooks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('secret', sa.String(length=100), nullable=True),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('total_deliveries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_deliveries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_deliveries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('webhook_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for webhooks
    op.create_index('ix_webhooks_tenant_id', 'webhooks', ['tenant_id'])
    op.create_index('ix_webhooks_is_deleted', 'webhooks', ['is_deleted'])
    
    # Create webhook_deliveries table
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('webhook_id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('attempted_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for webhook_deliveries
    op.create_index('ix_webhook_deliveries_webhook_id', 'webhook_deliveries', ['webhook_id'])
    op.create_index('ix_webhook_deliveries_event_type', 'webhook_deliveries', ['event_type'])
    op.create_index('ix_webhook_deliveries_status', 'webhook_deliveries', ['status'])


def downgrade() -> None:
    """Drop webhooks and webhook_deliveries tables."""
    
    # Drop indexes
    op.drop_index('ix_webhook_deliveries_status', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_event_type', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_webhook_id', table_name='webhook_deliveries')
    op.drop_index('ix_webhooks_is_deleted', table_name='webhooks')
    op.drop_index('ix_webhooks_tenant_id', table_name='webhooks')
    
    # Drop tables
    op.drop_table('webhook_deliveries')
    op.drop_table('webhooks')
