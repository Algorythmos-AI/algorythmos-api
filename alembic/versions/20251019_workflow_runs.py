"""Add workflow_runs table (Sprint 6 - P5.1-P5.2)

Revision ID: 20251019_workflow_runs
Revises: 20251019_runs_version_tracking
Create Date: 2025-10-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20251019_workflow_runs'
down_revision = '20251019_runs_version_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create workflow_runs table for workflow execution tracking."""
    
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workflow_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=True),
        
        # Status and results
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=True),
        sa.Column('output', sa.JSON(), nullable=True),
        sa.Column('error', sa.JSON(), nullable=True),
        
        # Corrections (Sprint 6 - P5.2)
        sa.Column('corrections', sa.JSON(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        
        # API version tracking
        sa.Column('api_version', sa.String(length=50), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        
        # Metadata
        sa.Column('run_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_workflow_runs_workflow_id', 'workflow_runs', ['workflow_id'])
    op.create_index('ix_workflow_runs_tenant_id', 'workflow_runs', ['tenant_id'])
    op.create_index('ix_workflow_runs_file_id', 'workflow_runs', ['file_id'])
    op.create_index('ix_workflow_runs_status', 'workflow_runs', ['status'])
    op.create_index('ix_workflow_runs_is_deleted', 'workflow_runs', ['is_deleted'])
    
    # Create compound index for common queries
    op.create_index(
        'ix_workflow_runs_tenant_workflow',
        'workflow_runs',
        ['tenant_id', 'workflow_id', 'status'],
        unique=False
    )


def downgrade() -> None:
    """Drop workflow_runs table."""
    
    op.drop_index('ix_workflow_runs_tenant_workflow', 'workflow_runs')
    op.drop_index('ix_workflow_runs_is_deleted', 'workflow_runs')
    op.drop_index('ix_workflow_runs_status', 'workflow_runs')
    op.drop_index('ix_workflow_runs_file_id', 'workflow_runs')
    op.drop_index('ix_workflow_runs_tenant_id', 'workflow_runs')
    op.drop_index('ix_workflow_runs_workflow_id', 'workflow_runs')
    op.drop_table('workflow_runs')
