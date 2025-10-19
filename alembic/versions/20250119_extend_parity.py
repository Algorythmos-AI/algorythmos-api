"""Create processors, workflows, and evaluation sets tables

Revision ID: 20250119_extend_parity
Revises: 20250119_webhooks
Create Date: 2025-01-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers
revision = '20250119_extend_parity'
down_revision = '20250119_webhooks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create processors, workflows, and evaluation sets tables."""
    
    # Create processors table
    op.create_table(
        'processors',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('processor_type', sa.String(length=50), nullable=False),
        sa.Column('implementation', sa.JSON(), nullable=False),
        sa.Column('input_schema', sa.JSON(), nullable=True),
        sa.Column('output_schema', sa.JSON(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('processor_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_processors_tenant_id', 'processors', ['tenant_id'])
    op.create_index('ix_processors_is_deleted', 'processors', ['is_deleted'])
    
    # Create workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('workflow_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workflows_tenant_id', 'workflows', ['tenant_id'])
    op.create_index('ix_workflows_is_deleted', 'workflows', ['is_deleted'])
    
    # Create evaluation_sets table
    op.create_table(
        'evaluation_sets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('test_cases', sa.JSON(), nullable=False),
        sa.Column('target_type', sa.String(length=50), nullable=False),
        sa.Column('target_id', sa.String(), nullable=True),
        sa.Column('evaluation_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_evaluation_sets_tenant_id', 'evaluation_sets', ['tenant_id'])
    op.create_index('ix_evaluation_sets_is_deleted', 'evaluation_sets', ['is_deleted'])
    op.create_index('ix_evaluation_sets_target_type', 'evaluation_sets', ['target_type'])


def downgrade() -> None:
    """Drop processors, workflows, and evaluation sets tables."""
    op.drop_index('ix_evaluation_sets_target_type', 'evaluation_sets')
    op.drop_index('ix_evaluation_sets_is_deleted', 'evaluation_sets')
    op.drop_index('ix_evaluation_sets_tenant_id', 'evaluation_sets')
    op.drop_table('evaluation_sets')
    
    op.drop_index('ix_workflows_is_deleted', 'workflows')
    op.drop_index('ix_workflows_tenant_id', 'workflows')
    op.drop_table('workflows')
    
    op.drop_index('ix_processors_is_deleted', 'processors')
    op.drop_index('ix_processors_tenant_id', 'processors')
    op.drop_table('processors')
