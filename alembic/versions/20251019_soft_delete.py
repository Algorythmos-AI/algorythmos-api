"""add soft delete columns

Revision ID: 20251019_soft_delete
Revises: 20251019_generic_doc
Create Date: 2025-10-19 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251019_soft_delete'
down_revision = '20251019_generic_doc'
branch_labels = None
depends_on = None


def upgrade():
    """Add is_deleted column to processing tables."""
    # Add is_deleted to extraction_schemas
    op.add_column('extraction_schemas', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_extraction_schemas_is_deleted', 'extraction_schemas', ['is_deleted'])
    
    # Add is_deleted to extractors
    op.add_column('extractors', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_extractors_is_deleted', 'extractors', ['is_deleted'])
    
    # Add is_deleted to classifiers
    op.add_column('classifiers', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_classifiers_is_deleted', 'classifiers', ['is_deleted'])
    
    # Add is_deleted to splitters
    op.add_column('splitters', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_splitters_is_deleted', 'splitters', ['is_deleted'])


def downgrade():
    """Remove is_deleted column from processing tables."""
    op.drop_index('ix_splitters_is_deleted', table_name='splitters')
    op.drop_column('splitters', 'is_deleted')
    
    op.drop_index('ix_classifiers_is_deleted', table_name='classifiers')
    op.drop_column('classifiers', 'is_deleted')
    
    op.drop_index('ix_extractors_is_deleted', table_name='extractors')
    op.drop_column('extractors', 'is_deleted')
    
    op.drop_index('ix_extraction_schemas_is_deleted', table_name='extraction_schemas')
    op.drop_column('extraction_schemas', 'is_deleted')
