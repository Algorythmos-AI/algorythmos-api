"""add generic document processing tables

Revision ID: 20251019_generic_doc
Revises: 202410052101
Create Date: 2025-10-19 19:30:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251019_generic_doc'
down_revision = '202410052101'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add tables for generic document processing."""
    
    # Create extraction_schemas table
    op.create_table(
        'extraction_schemas',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_extraction_schemas_tenant_id', 'extraction_schemas', ['tenant_id'])
    
    # Create extractors table
    op.create_table(
        'extractors',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('schema_id', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('rules', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_extractors_tenant_id', 'extractors', ['tenant_id'])
    op.create_index('ix_extractors_schema_id', 'extractors', ['schema_id'])
    
    # Create classifiers table
    op.create_table(
        'classifiers',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('categories', sa.JSON(), nullable=False),
        sa.Column('rules', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_classifiers_tenant_id', 'classifiers', ['tenant_id'])
    
    # Create splitters table
    op.create_table(
        'splitters',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('rules', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_splitters_tenant_id', 'splitters', ['tenant_id'])
    
    # Create document_chunks table
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('parent_document_id', sa.String(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_range_start', sa.Integer(), nullable=True),
        sa.Column('page_range_end', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=False, server_default='application/pdf'),
        sa.Column('content_size', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_document_chunks_parent_document_id', 'document_chunks', ['parent_document_id'])
    
    # Create extraction_results table
    op.create_table(
        'extraction_results',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('schema_id', sa.String(), nullable=False),
        sa.Column('extractor_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('fields', sa.JSON(), nullable=False),
        sa.Column('overall_confidence', sa.Integer(), nullable=False),
        sa.Column('warnings', sa.JSON(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_extraction_results_document_id', 'extraction_results', ['document_id'])
    op.create_index('ix_extraction_results_schema_id', 'extraction_results', ['schema_id'])
    op.create_index('ix_extraction_results_tenant_id', 'extraction_results', ['tenant_id'])


def downgrade() -> None:
    """Remove generic document processing tables."""
    
    op.drop_index('ix_extraction_results_tenant_id', table_name='extraction_results')
    op.drop_index('ix_extraction_results_schema_id', table_name='extraction_results')
    op.drop_index('ix_extraction_results_document_id', table_name='extraction_results')
    op.drop_table('extraction_results')
    
    op.drop_index('ix_document_chunks_parent_document_id', table_name='document_chunks')
    op.drop_table('document_chunks')
    
    op.drop_index('ix_splitters_tenant_id', table_name='splitters')
    op.drop_table('splitters')
    
    op.drop_index('ix_classifiers_tenant_id', table_name='classifiers')
    op.drop_table('classifiers')
    
    op.drop_index('ix_extractors_schema_id', table_name='extractors')
    op.drop_index('ix_extractors_tenant_id', table_name='extractors')
    op.drop_table('extractors')
    
    op.drop_index('ix_extraction_schemas_tenant_id', table_name='extraction_schemas')
    op.drop_table('extraction_schemas')
