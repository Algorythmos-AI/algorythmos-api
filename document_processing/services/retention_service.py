"""Data retention: remove customer documents and everything derived from them.

Policy (settings):
- ``RETENTION_DAYS`` (30): uploaded documents and derived data (parse runs,
  extraction results, chunks, job payloads and results, webhook deliveries)
  are removed this many days after creation.
- ``SOFT_DELETE_PURGE_DAYS`` (7): rows the user deleted (``is_deleted``) are
  removed this many days after deletion (``updated_at`` records the deletion).
  This also covers configuration objects, which otherwise do not expire.
- Rows past their own ``expires_at`` (idempotency cache, webhook replay
  guard) are removed.

``RETENTION_MODE=report`` (the default) only counts what would be removed.
``enforce`` deletes. Runs are idempotent and safe to repeat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

# Document data and everything derived from it: expires by age.
EXPIRING_TABLES = (
    "files",
    "parser_runs",
    "parser_run_jobs",
    "extraction_results",
    "document_chunks",
    "runs",
    "background_jobs",
    "workflow_runs",
    "webhook_deliveries",
)

# Tables with a soft-delete flag: purged once deleted for long enough.
SOFT_DELETE_TABLES = (
    "files",
    "workflow_runs",
    "extraction_schemas",
    "extractors",
    "classifiers",
    "splitters",
    "processors",
    "processor_versions",
    "workflows",
    "webhooks",
    "evaluation_sets",
    "eval_items",
)

# Short-lived operational rows that carry their own expiry.
TTL_TABLES = ("idempotency_keys", "webhook_replay_events")

# Columns stored with a time zone; every other timestamp column is naive UTC.
_TZ_AWARE_TABLES = frozenset({"runs"})

# Arbitrary constant identifying the retention job's Postgres advisory lock.
ADVISORY_LOCK_KEY = 7_431_220_925


@dataclass(frozen=True)
class RetentionPolicy:
    retention_days: int
    soft_delete_days: int

    def __post_init__(self) -> None:
        if self.retention_days < 1 or self.soft_delete_days < 1:
            raise ValueError("retention periods must be at least one day")


@dataclass(frozen=True)
class RetentionResult:
    mode: str
    counts: dict[str, int]
    skipped: bool = False

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _cutoff(now_utc: datetime, table: str, days: int) -> datetime:
    moment = now_utc - timedelta(days=days)
    return moment if table in _TZ_AWARE_TABLES else moment.replace(tzinfo=None)


def _conditions(now_utc: datetime, policy: RetentionPolicy) -> dict[str, sa.ColumnElement[bool]]:
    """One WHERE clause per table (ORed together when a table appears in several groups)."""
    conditions: dict[str, list[sa.ColumnElement[bool]]] = {}

    for name in EXPIRING_TABLES:
        column = sa.column("created_at")
        conditions.setdefault(name, []).append(column < _cutoff(now_utc, name, policy.retention_days))

    for name in SOFT_DELETE_TABLES:
        clause = sa.and_(
            sa.column("is_deleted").is_(True),
            sa.column("updated_at") < _cutoff(now_utc, name, policy.soft_delete_days),
        )
        conditions.setdefault(name, []).append(clause)

    for name in TTL_TABLES:
        conditions.setdefault(name, []).append(sa.column("expires_at") < _cutoff(now_utc, name, 0))

    return {name: sa.or_(*clauses) for name, clauses in conditions.items()}


async def _try_lock(session) -> bool:
    """Transaction-scoped advisory lock: released automatically on commit or rollback,
    so it can never outlive the run (a session-level lock could stay held on a
    pooled connection)."""
    if session.bind.dialect.name != "postgresql":
        return True
    result = await session.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
    )
    return bool(result.scalar())


async def run_retention(
    session,
    policy: RetentionPolicy,
    *,
    enforce: bool,
    now_utc: datetime | None = None,
) -> RetentionResult:
    """Count (report) or delete (enforce) rows past the retention policy.

    Only one run proceeds at a time on Postgres (transaction advisory lock); a
    concurrent run returns ``skipped=True`` without touching data.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    mode = "enforce" if enforce else "report"

    if not await _try_lock(session):
        await session.rollback()
        return RetentionResult(mode=mode, counts={}, skipped=True)

    counts: dict[str, int] = {}
    try:
        for name, where in _conditions(now_utc, policy).items():
            table = sa.table(name)
            count = (await session.execute(sa.select(sa.func.count()).select_from(table).where(where))).scalar_one()
            if count and enforce:
                await session.execute(sa.delete(table).where(where))
            counts[name] = int(count)
        if enforce:
            await session.commit()
        else:
            await session.rollback()
    except Exception:
        await session.rollback()
        raise

    return RetentionResult(mode=mode, counts=counts)
