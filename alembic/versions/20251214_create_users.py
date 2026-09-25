"""create users table

Revision ID: 20251214_users
Revises: 20251019_workflow_runs
Create Date: 2025-12-14

This migration creates the users table for human identity persistence.
The table stores minimal user information from Google OAuth authentication.

Schema follows the minimal safe design specified in requirements:
- id (UUID, primary key)
- email (unique, not null) - unique identifier
- display_name - from Google profile
- avatar_url - from Google profile
- provider ("google") - auth provider for future SSO support
- provider_account_id - Google's 'sub' claim
- created_at - first login timestamp
- last_login_at - updated on every login
- is_active - soft-disable capability
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251214_users"
down_revision = "20251019_workflow_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="google"),
        sa.Column("provider_account_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Create indexes for efficient queries
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_is_active", "users", ["is_active"])
    op.create_index("ix_users_provider", "users", ["provider"])
    op.create_index("ix_users_provider_account_id", "users", ["provider_account_id"])


def downgrade() -> None:
    op.drop_index("ix_users_provider_account_id", table_name="users")
    op.drop_index("ix_users_provider", table_name="users")
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
