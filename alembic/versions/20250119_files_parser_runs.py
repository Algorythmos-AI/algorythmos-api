"""add files and parser_runs tables

Revision ID: 20250119_files_parser_runs
Revises: 20251019_soft_delete
Create Date: 2025-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250119_files_parser_runs'
down_revision = '20251019_soft_delete'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create files and parser_runs tables."""
    
    # Create files table
    op.create_table(
        'files',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('file_metadata', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for files
    op.create_index('ix_files_tenant_id', 'files', ['tenant_id'])
    op.create_index('ix_files_is_deleted', 'files', ['is_deleted'])
    
    # Create parser_runs table
    op.create_table(
        'parser_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('schema_id', sa.String(), nullable=True),
        sa.Column('extractor_id', sa.String(), nullable=True),
        sa.Column('classifier_id', sa.String(), nullable=True),
        sa.Column('splitter_id', sa.String(), nullable=True),
        sa.Column('classification_result', sa.JSON(), nullable=True),
        sa.Column('split_chunks', sa.JSON(), nullable=True),
        sa.Column('extracted_data', sa.JSON(), nullable=True),
        sa.Column('confidence_score', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('run_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes for parser_runs
    op.create_index('ix_parser_runs_tenant_id', 'parser_runs', ['tenant_id'])
    op.create_index('ix_parser_runs_file_id', 'parser_runs', ['file_id'])
    op.create_index('ix_parser_runs_status', 'parser_runs', ['status'])


def downgrade() -> None:
    """Drop files and parser_runs tables."""
    
    # Drop indexes
    op.drop_index('ix_parser_runs_status', table_name='parser_runs')
    op.drop_index('ix_parser_runs_file_id', table_name='parser_runs')
    op.drop_index('ix_parser_runs_tenant_id', table_name='parser_runs')
    op.drop_index('ix_files_is_deleted', table_name='files')
    op.drop_index('ix_files_tenant_id', table_name='files')
    
    # Drop tables
    op.drop_table('parser_runs')
    op.drop_table('files')
