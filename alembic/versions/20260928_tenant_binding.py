"""bind users and API keys to a tenant

Revision ID: 20260928_tenant_binding
Revises: 20260211_distributed_state
Create Date: 2026-09-28

Expand-only: adds a nullable, indexed ``tenant_id`` to ``users`` and
``api_keys``. Existing rows keep NULL and get their tenant the next time they
authenticate (core/principals.py), so no backfill runs here and code without
this column keeps working.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260928_tenant_binding"
down_revision = "20260211_distributed_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tenant_id", sa.String(255), nullable=True))
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.add_column("api_keys", sa.Column("tenant_id", sa.String(255), nullable=True))
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_tenant_id", table_name="api_keys")
    op.drop_column("api_keys", "tenant_id")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("users", "tenant_id")
