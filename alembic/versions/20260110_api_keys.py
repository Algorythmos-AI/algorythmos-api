"""create api_keys table

Revision ID: 20260110_api_keys
Revises: 20251214_users
Create Date: 2026-01-10

This migration creates the api_keys table for programmatic API authentication.
API keys are hashed (SHA-256) before storage - raw keys are never persisted.

Schema:
- id (UUID, primary key)
- user_id (foreign key to users.id)
- name (user-defined key name)
- key_hash (SHA-256 hash of the full key, unique)
- prefix (first 12 chars of key for display: "alg_" + 8 chars)
- created_at (timestamp)
- last_used_at (nullable timestamp)
- is_active (soft delete flag)
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260110_api_keys"
down_revision = "20251214_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),  # SHA-256 = 64 hex chars
        sa.Column("prefix", sa.String(12), nullable=False),  # "alg_" + 8 chars
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    
    # Create indexes for efficient queries
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_is_active", "api_keys", ["is_active"])
    op.create_index("ix_api_keys_user_active", "api_keys", ["user_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_user_active", table_name="api_keys")
    op.drop_index("ix_api_keys_is_active", table_name="api_keys")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")
