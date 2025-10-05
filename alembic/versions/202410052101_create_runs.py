"""create runs table

Revision ID: 202410052101
Revises: 
Create Date: 2024-10-05 21:01:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202410052101"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("processor", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("vendor_job_id", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    op.create_index("ix_runs_processor", "runs", ["processor"])
    op.create_index("ix_runs_tenant_id", "runs", ["tenant_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_idempotency_key", "runs", ["idempotency_key"])
    op.create_unique_constraint("uq_runs_vendor_job_id", "runs", ["vendor_job_id"])
    op.create_index(
        "uq_runs_tenant_proc_idem",
        "runs",
        ["tenant_id", "processor", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_runs_tenant_proc_idem", table_name="runs")
    op.drop_constraint("uq_runs_vendor_job_id", "runs", type_="unique")
    op.drop_index("ix_runs_idempotency_key", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_tenant_id", table_name="runs")
    op.drop_index("ix_runs_processor", table_name="runs")
    op.drop_table("runs")
