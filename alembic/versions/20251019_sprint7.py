"""sprint7_eval_items_webhook_version

Revision ID: 20251019_sprint7
Revises: 20251019_workflow_runs
Create Date: 2025-01-19

Sprint 7 (P6.1, P7.1): Evaluation Items Bulk + Webhook Version Echo

Changes:
- Create eval_items table for individual test cases within evaluation sets
- Add api_version column to webhook_deliveries table for version echo tracking

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20251019_sprint7'
down_revision: Union[str, None] = '20251019_workflow_runs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create eval_items table and add api_version to webhook_deliveries.
    
    Sprint 7 Features:
    - P6.1: Bulk evaluation item creation
    - P7.1: Webhook version header echo
    """
    
    # Create eval_items table
    op.create_table(
        'eval_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('evaluation_set_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('input_data', sa.JSON(), nullable=False),
        sa.Column('expected_output', sa.JSON(), nullable=False),
        sa.Column('actual_output', sa.JSON(), nullable=True),
        sa.Column('last_run_status', sa.String(length=20), nullable=True),
        sa.Column('last_run_score', sa.Float(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('item_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for eval_items
    op.create_index('ix_eval_items_evaluation_set_id', 'eval_items', ['evaluation_set_id'])
    op.create_index('ix_eval_items_tenant_id', 'eval_items', ['tenant_id'])
    op.create_index('ix_eval_items_is_deleted', 'eval_items', ['is_deleted'])
    op.create_index('ix_eval_items_last_run_status', 'eval_items', ['last_run_status'])
    
    # Add compound index for common query pattern
    op.create_index(
        'ix_eval_items_set_tenant_deleted',
        'eval_items',
        ['evaluation_set_id', 'tenant_id', 'is_deleted']
    )
    
    # Add api_version column to webhook_deliveries (P7.1)
    op.add_column(
        'webhook_deliveries',
        sa.Column('api_version', sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    """Remove eval_items table and api_version column."""
    
    # Remove api_version column from webhook_deliveries
    op.drop_column('webhook_deliveries', 'api_version')
    
    # Drop indexes for eval_items
    op.drop_index('ix_eval_items_set_tenant_deleted', table_name='eval_items')
    op.drop_index('ix_eval_items_last_run_status', table_name='eval_items')
    op.drop_index('ix_eval_items_is_deleted', table_name='eval_items')
    op.drop_index('ix_eval_items_tenant_id', table_name='eval_items')
    op.drop_index('ix_eval_items_evaluation_set_id', table_name='eval_items')
    
    # Drop eval_items table
    op.drop_table('eval_items')
