"""Add durable operational state tables for async processing.

Revision ID: 20260211_distributed_state
Revises: 20260211_merge_runtime_heads
Create Date: 2026-02-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260211_distributed_state"
down_revision: Union[str, None] = "20260211_merge_runtime_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("cache_key", sa.String(length=255), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("request_method", sa.String(length=10), nullable=False),
        sa.Column("request_path", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("in_progress", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("cache_key"),
    )
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])
    op.create_index("ix_idempotency_keys_idempotency_key", "idempotency_keys", ["idempotency_key"])
    op.create_index("ix_idempotency_keys_in_progress", "idempotency_keys", ["in_progress"])
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    op.create_table(
        "webhook_replay_events",
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_webhook_replay_events_expires_at", "webhook_replay_events", ["expires_at"])

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_jobs_tenant_id", "background_jobs", ["tenant_id"])
    op.create_index("ix_background_jobs_status", "background_jobs", ["status"])

    op.create_table(
        "parser_run_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("lock_owner", sa.String(length=128), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_parser_run_jobs_run_id"),
    )
    op.create_index("ix_parser_run_jobs_run_id", "parser_run_jobs", ["run_id"])
    op.create_index("ix_parser_run_jobs_tenant_id", "parser_run_jobs", ["tenant_id"])
    op.create_index("ix_parser_run_jobs_status", "parser_run_jobs", ["status"])
    op.create_index("ix_parser_run_jobs_next_attempt_at", "parser_run_jobs", ["next_attempt_at"])
    op.create_index("ix_parser_run_jobs_lock_owner", "parser_run_jobs", ["lock_owner"])
    op.create_index("ix_parser_run_jobs_locked_at", "parser_run_jobs", ["locked_at"])
    op.create_index("ix_parser_run_jobs_dead_lettered_at", "parser_run_jobs", ["dead_lettered_at"])


def downgrade() -> None:
    op.drop_index("ix_parser_run_jobs_dead_lettered_at", table_name="parser_run_jobs")
    op.drop_index("ix_parser_run_jobs_locked_at", table_name="parser_run_jobs")
    op.drop_index("ix_parser_run_jobs_lock_owner", table_name="parser_run_jobs")
    op.drop_index("ix_parser_run_jobs_next_attempt_at", table_name="parser_run_jobs")
    op.drop_index("ix_parser_run_jobs_status", table_name="parser_run_jobs")
    op.drop_index("ix_parser_run_jobs_tenant_id", table_name="parser_run_jobs")
    op.drop_index("ix_parser_run_jobs_run_id", table_name="parser_run_jobs")
    op.drop_table("parser_run_jobs")

    op.drop_index("ix_background_jobs_status", table_name="background_jobs")
    op.drop_index("ix_background_jobs_tenant_id", table_name="background_jobs")
    op.drop_table("background_jobs")

    op.drop_index("ix_webhook_replay_events_expires_at", table_name="webhook_replay_events")
    op.drop_table("webhook_replay_events")

    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_in_progress", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_idempotency_key", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_tenant_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
