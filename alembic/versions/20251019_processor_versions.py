"""Add processor_versions table (Sprint 4 - P3.1-P3.2)

Revision ID: 20251019_processor_versions
Revises: 20250119_extend_parity
Create Date: 2025-10-19

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20251019_processor_versions'
down_revision = '20250119_extend_parity'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create processor_versions table for processor versioning support."""
    
    op.create_table(
        'processor_versions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('processor_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        
        # Version content (snapshot of processor)
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('processor_type', sa.String(length=50), nullable=False),
        sa.Column('implementation', sa.JSON(), nullable=False),
        sa.Column('input_schema', sa.JSON(), nullable=True),
        sa.Column('output_schema', sa.JSON(), nullable=True),
        
        # Version lifecycle
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('deprecated_at', sa.DateTime(), nullable=True),
        
        # Change tracking
        sa.Column('change_notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        
        # Metadata
        sa.Column('version_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_processor_versions_processor_id', 'processor_versions', ['processor_id'])
    op.create_index('ix_processor_versions_tenant_id', 'processor_versions', ['tenant_id'])
    op.create_index('ix_processor_versions_status', 'processor_versions', ['status'])
    op.create_index('ix_processor_versions_is_default', 'processor_versions', ['is_default'])
    op.create_index('ix_processor_versions_is_deleted', 'processor_versions', ['is_deleted'])
    
    # Create compound index for finding default versions
    op.create_index(
        'ix_processor_versions_proc_default',
        'processor_versions',
        ['processor_id', 'is_default', 'status'],
        unique=False
    )


def downgrade() -> None:
    """Drop processor_versions table."""
    
    op.drop_index('ix_processor_versions_proc_default', 'processor_versions')
    op.drop_index('ix_processor_versions_is_deleted', 'processor_versions')
    op.drop_index('ix_processor_versions_is_default', 'processor_versions')
    op.drop_index('ix_processor_versions_status', 'processor_versions')
    op.drop_index('ix_processor_versions_tenant_id', 'processor_versions')
    op.drop_index('ix_processor_versions_processor_id', 'processor_versions')
    op.drop_table('processor_versions')
