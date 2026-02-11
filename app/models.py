from __future__ import annotations

from sqlalchemy import DateTime, JSON, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Index

from database import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    processor: Mapped[str] = mapped_column(String, index=True, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    vendor_job_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Sprint 5: Version tracking
    processor_version_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    version_number: Mapped[int | None] = mapped_column(nullable=True)
    api_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    
    # Timestamps
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_runs_tenant_proc_idem",
            "tenant_id",
            "processor",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index("ix_runs_idempotency_key", "idempotency_key"),
    )
