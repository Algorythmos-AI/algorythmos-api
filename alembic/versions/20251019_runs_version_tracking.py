"""Add processor version tracking to runs (Sprint 5 - P4.1)

Revision ID: 20251019_runs_version_tracking
Revises: 20251019_processor_versions
Create Date: 2025-10-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20251019_runs_version_tracking'
down_revision = '20251019_processor_versions'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add version tracking columns to runs table."""
    
    # Add processor_version_id column
    op.add_column('runs', sa.Column('processor_version_id', sa.String(), nullable=True))
    op.create_index('ix_runs_processor_version_id', 'runs', ['processor_version_id'])
    
    # Add version_number for quick reference
    op.add_column('runs', sa.Column('version_number', sa.Integer(), nullable=True))
    
    # Add api_version to track which API version was used
    op.add_column('runs', sa.Column('api_version', sa.String(length=50), nullable=True))
    
    # Add timestamps for tracking run lifecycle
    op.add_column('runs', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('runs', sa.Column('completed_at', sa.DateTime(), nullable=True))
    
    # Add file_id reference for tracking input
    op.add_column('runs', sa.Column('file_id', sa.String(), nullable=True))
    op.create_index('ix_runs_file_id', 'runs', ['file_id'])


def downgrade() -> None:
    """Remove version tracking columns from runs table."""
    
    op.drop_index('ix_runs_file_id', 'runs')
    op.drop_column('runs', 'file_id')
    op.drop_column('runs', 'completed_at')
    op.drop_column('runs', 'started_at')
    op.drop_column('runs', 'api_version')
    op.drop_column('runs', 'version_number')
    op.drop_index('ix_runs_processor_version_id', 'runs')
    op.drop_column('runs', 'processor_version_id')
