"""merge sprint7 and api_keys heads

Revision ID: 20260211_merge_heads
Revises: 20251019_sprint7, 20260110_api_keys
Create Date: 2026-02-11

This is a merge migration that unifies two independent branches:
- 20251019_sprint7 (eval_items + webhook api_version)
- 20260110_api_keys (users + api_keys tables)

No schema changes needed — the branches don't conflict.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260211_merge_heads'
down_revision = ('20251019_sprint7', '20260110_api_keys')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
