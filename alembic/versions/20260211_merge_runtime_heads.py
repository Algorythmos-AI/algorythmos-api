"""Merge split Alembic heads after runtime unification.

Revision ID: 20260211_merge_runtime_heads
Revises: 20260110_api_keys, 20251019_sprint7
Create Date: 2026-02-11
"""

from __future__ import annotations

from typing import Sequence

# revision identifiers, used by Alembic.
revision: str = "20260211_merge_runtime_heads"
down_revision: str | Sequence[str] | None = ("20260110_api_keys", "20251019_sprint7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge revision with no schema changes."""


def downgrade() -> None:
    """Split merge revision with no schema changes."""
