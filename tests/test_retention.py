"""Data retention: policy, safety defaults and the scheduled endpoint.

Seeds one row of each kind (a document, a run with a time-zone-aware
timestamp, an idempotency record, a soft-deleted configuration object), each
old enough to go and a twin young enough to stay, then checks report mode
deletes nothing and enforce mode deletes exactly the old rows.

Set RETENTION_TEST_DATABASE_URL (a migrated Postgres database) to also run the
same checks on Postgres, where time-zone handling and the advisory lock matter.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Run
from config import settings
from document_processing.models import FileDB
from document_processing.services.retention_service import RetentionPolicy, run_retention

app_main = sys.modules["app_main"]
NOW = datetime.now(timezone.utc)
POLICY = RetentionPolicy(retention_days=30, soft_delete_days=7)
TABLES = ("files", "runs", "idempotency_keys", "extractors")


def _naive(moment: datetime) -> datetime:
    return moment.replace(tzinfo=None)


async def _insert(session, name: str, values: dict) -> None:
    # Typed columns where the driver needs them (JSON for dict values).
    columns = (sa.column(key, sa.JSON) if isinstance(value, dict) else sa.column(key) for key, value in values.items())
    await session.execute(sa.insert(sa.table(name, *columns)).values(values))


async def _seed(session, tag: str) -> None:
    old, young = NOW - timedelta(days=45), NOW - timedelta(days=2)
    for age, suffix in ((old, "old"), (young, "new")):
        await _insert(
            session,
            "files",
            (
                {
                    "id": f"{tag}-file-{suffix}", "tenant_id": tag, "filename": "synthetic.pdf",
                    "content_type": "application/pdf", "size_bytes": 1, "storage_path": "x", "checksum": "0",
                    "is_deleted": False, "created_at": _naive(age), "updated_at": _naive(age),
                }
            )
        )
        await _insert(
            session,
            "runs",
            (
                {"id": f"{tag}-run-{suffix}", "processor": "p", "status": "done", "created_at": age, "updated_at": age}
            )
        )
        await _insert(
            session,
            "idempotency_keys",
            (
                {
                    "cache_key": f"{tag}-idem-{suffix}", "request_method": "POST", "request_path": "/x",
                    "idempotency_key": suffix, "in_progress": False,
                    "created_at": _naive(age), "updated_at": _naive(age),
                    # Old row expired 15 days ago; young row expires in 28 days.
                    "expires_at": _naive(age + timedelta(days=30)),
                }
            )
        )
        # A deleted configuration object: removed 7 days after deletion.
        await _insert(
            session,
            "extractors",
            (
                {
                    "id": f"{tag}-extractor-{suffix}", "tenant_id": tag, "name": "e", "type": "regex",
                    "schema_id": "s", "rules": {}, "enabled": True, "priority": 100, "is_deleted": True,
                    "created_at": _naive(old), "updated_at": _naive(age),
                }
            )
        )
    await session.commit()


async def _remaining(session, tag: str) -> set[str]:
    left: set[str] = set()
    for name in TABLES:
        key = "cache_key" if name == "idempotency_keys" else "id"
        rows = await session.execute(
            sa.select(sa.column(key)).select_from(sa.table(name)).where(sa.column(key).like(f"{tag}-%"))
        )
        left |= {row[0] for row in rows}
    return left


async def _exercise(factory) -> None:
    tag = f"ret{uuid4().hex[:8]}"
    async with factory() as session:
        await _seed(session, tag)

    async with factory() as session:
        report = await run_retention(session, POLICY, enforce=False, now_utc=NOW)
    assert report.mode == "report" and not report.skipped
    for name in TABLES:
        assert report.counts[name] >= 1, (name, report.counts)
    async with factory() as session:
        assert len(await _remaining(session, tag)) == 8, "report mode must not delete"

    async with factory() as session:
        enforced = await run_retention(session, POLICY, enforce=True, now_utc=NOW)
    assert enforced.mode == "enforce"
    async with factory() as session:
        assert await _remaining(session, tag) == {
            f"{tag}-file-new", f"{tag}-run-new", f"{tag}-idem-new", f"{tag}-extractor-new",
        }

    async with factory() as session:
        again = await run_retention(session, POLICY, enforce=True, now_utc=NOW)
    assert all(again.counts[name] == 0 for name in TABLES), again.counts


@pytest.fixture
async def sqlite_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retention.db'}")
    async with engine.begin() as conn:
        # The full schema: the retention job checks every table it covers.
        await conn.run_sync(FileDB.metadata.create_all)
        await conn.run_sync(Run.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


def test_policy_rejects_zero_days() -> None:
    with pytest.raises(ValueError):
        RetentionPolicy(retention_days=0, soft_delete_days=7)


async def test_report_then_enforce_on_sqlite(sqlite_factory) -> None:
    await _exercise(sqlite_factory)


@pytest.mark.skipif(not os.getenv("RETENTION_TEST_DATABASE_URL"), reason="needs a migrated Postgres database")
async def test_report_then_enforce_on_postgres() -> None:
    engine = create_async_engine(os.environ["RETENTION_TEST_DATABASE_URL"])
    try:
        await _exercise(async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
        # A second run while one holds the lock is skipped, not run twice.
        async with engine.connect() as holder:
            await holder.execute(sa.text("SELECT pg_advisory_xact_lock(7431220925)"))
            factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            async with factory() as session:
                assert (await run_retention(session, POLICY, enforce=True, now_utc=NOW)).skipped
            await holder.rollback()
    finally:
        await engine.dispose()


# --- scheduled endpoint -----------------------------------------------------------


@pytest.fixture
def cron_secret(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "cron-test-secret")
    return "cron-test-secret"


async def test_cron_fails_closed_without_configured_secret(app_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "CRON_SECRET", None)
    response = await app_client.get("/internal/cron/retention", headers={"Authorization": "Bearer anything"})
    assert response.status_code == 401


async def test_cron_rejects_wrong_secret(app_client: AsyncClient, cron_secret) -> None:
    response = await app_client.get("/internal/cron/retention", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_cron_refuses_outside_production(app_client: AsyncClient, cron_secret, monkeypatch) -> None:
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    response = await app_client.get("/internal/cron/retention", headers={"Authorization": f"Bearer {cron_secret}"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "RETENTION_PRODUCTION_ONLY"


async def test_cron_defaults_to_report_mode(app_client: AsyncClient, cron_secret, sqlite_factory, monkeypatch) -> None:
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setattr(settings, "RETENTION_MODE", "report")

    async def _session():
        async with sqlite_factory() as session:
            yield session

    tag = f"cron{uuid4().hex[:6]}"
    async with sqlite_factory() as session:
        await _seed(session, tag)

    app_main.app.dependency_overrides[app_main._db_session] = _session
    try:
        response = await app_client.get(
            "/internal/cron/retention", headers={"Authorization": f"Bearer {cron_secret}"}
        )
    finally:
        app_main.app.dependency_overrides.pop(app_main._db_session, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "report" and body["total"] >= 4
    async with sqlite_factory() as session:
        assert len(await _remaining(session, tag)) == 8


async def test_cron_endpoint_hidden_from_openapi(app_client: AsyncClient) -> None:
    paths = (await app_client.get("/openapi.json")).json()["paths"]
    assert "/internal/cron/retention" not in paths
