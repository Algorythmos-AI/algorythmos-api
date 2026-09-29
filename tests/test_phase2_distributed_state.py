"""Phase 2 regression tests: durable state + async parser worker behaviour."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import Settings
from database import Base
from document_processing.models import FileDB, IdempotencyKeyDB, ParserRunDB, ParserRunJobDB
from document_processing.schemas import ParseResult, ParserRunStatus
from document_processing.services import parser_service
from document_processing.state import RedisRateLimitStore, SQLIdempotencyStore
from document_processing.workers import parse_worker


@pytest_asyncio.fixture
async def phase2_session_factory(tmp_path):
    """Create an isolated sqlite database for durable state tests."""
    db_path = tmp_path / "phase2_state.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    FileDB.__table__,
                    ParserRunDB.__table__,
                    ParserRunJobDB.__table__,
                    IdempotencyKeyDB.__table__,
                ],
            )
        )

    try:
        yield session_factory
    finally:
        await engine.dispose()


async def _seed_parser_run(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: str,
    run_id: str,
    file_id: str,
) -> None:
    now = datetime.utcnow()
    async with session_factory() as session:
        session.add(
            FileDB(
                id=file_id,
                tenant_id=tenant_id,
                filename="phase2.txt",
                content_type="text/plain",
                size_bytes=32,
                storage_path="phase2.txt",
                checksum="deadbeef",
                file_metadata={},
                is_deleted=False,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            ParserRunDB(
                id=run_id,
                tenant_id=tenant_id,
                file_id=file_id,
                status="pending",
                schema_id=None,
                extractor_id=None,
                classifier_id=None,
                splitter_id=None,
                run_metadata={},
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_sql_idempotency_store_is_durable_across_store_instances(phase2_session_factory):
    cache_key = "tenant-a:POST:/api/parse:key-1"
    store_one = SQLIdempotencyStore(phase2_session_factory)

    acquired = await store_one.acquire(
        cache_key=cache_key,
        tenant_id="tenant-a",
        idempotency_key="key-1",
        request_method="POST",
        request_path="/api/parse",
        ttl_seconds=300,
    )
    assert acquired.state == "reserved"

    await store_one.store_response(
        cache_key=cache_key,
        status_code=202,
        response_body={"run_id": "run_123"},
    )

    store_two = SQLIdempotencyStore(phase2_session_factory)
    replay = await store_two.acquire(
        cache_key=cache_key,
        tenant_id="tenant-a",
        idempotency_key="key-1",
        request_method="POST",
        request_path="/api/parse",
        ttl_seconds=300,
    )
    assert replay.state == "replay"
    assert replay.status_code == 202
    assert replay.response_body == {"run_id": "run_123"}


@pytest.mark.asyncio
async def test_parse_worker_processes_queued_job_to_success(phase2_session_factory, monkeypatch):
    tenant_id = "tenant-worker-success"
    run_id = "run_worker_success"
    file_id = "file_worker_success"
    await _seed_parser_run(
        phase2_session_factory,
        tenant_id=tenant_id,
        run_id=run_id,
        file_id=file_id,
    )

    async with phase2_session_factory() as session:
        await parser_service.enqueue_parser_run_job(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
            max_attempts=2,
        )

    monkeypatch.setattr(parse_worker, "async_session_factory", phase2_session_factory, raising=False)

    async def _fake_get_file_content(_file_db):
        return b"Worker success content"

    monkeypatch.setattr(parser_service.file_service, "get_file_content", _fake_get_file_content)

    processed = await parse_worker.process_next_parser_job(worker_id="phase2-worker-success")
    assert processed is True

    async with phase2_session_factory() as session:
        job_result = await session.execute(select(ParserRunJobDB).where(ParserRunJobDB.run_id == run_id))
        run_result = await session.execute(select(ParserRunDB).where(ParserRunDB.id == run_id))
        job = job_result.scalar_one()
        run = run_result.scalar_one()

    assert job.status == "succeeded"
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_parse_worker_retries_then_dead_letters_and_replay(phase2_session_factory, monkeypatch):
    tenant_id = "tenant-worker-fail"
    run_id = "run_worker_fail"
    file_id = "file_worker_fail"
    await _seed_parser_run(
        phase2_session_factory,
        tenant_id=tenant_id,
        run_id=run_id,
        file_id=file_id,
    )

    async with phase2_session_factory() as session:
        await parser_service.enqueue_parser_run_job(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
            max_attempts=2,
        )

    monkeypatch.setattr(parse_worker, "async_session_factory", phase2_session_factory, raising=False)
    monkeypatch.setattr(parse_worker.settings, "PARSE_WORKER_BASE_DELAY_S", 0.01, raising=False)
    monkeypatch.setattr(parse_worker.settings, "PARSE_WORKER_MAX_DELAY_S", 0.01, raising=False)
    monkeypatch.setattr(parse_worker.settings, "PARSE_WORKER_JITTER_S", 0.0, raising=False)

    async def _always_failed_result(session, tenant_id, run_id):  # noqa: ARG001
        return ParseResult(
            run_id=run_id,
            file_id=file_id,
            status="failed",
            classification=None,
            chunks=None,
            extracted=None,
            confidence=None,
            processing_time_ms=1,
            completed_at=datetime.utcnow(),
            error="forced failure",
        )

    monkeypatch.setattr(parse_worker.parser_service, "execute_parser_run", _always_failed_result)

    first_attempt = await parse_worker.process_next_parser_job(worker_id="phase2-worker-fail")
    assert first_attempt is True

    async with phase2_session_factory() as session:
        job_result = await session.execute(select(ParserRunJobDB).where(ParserRunJobDB.run_id == run_id))
        job = job_result.scalar_one()
        assert job.status == "failed"
        assert job.attempt_count == 1
        job.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        await session.commit()

    second_attempt = await parse_worker.process_next_parser_job(worker_id="phase2-worker-fail")
    assert second_attempt is True

    async with phase2_session_factory() as session:
        job_result = await session.execute(select(ParserRunJobDB).where(ParserRunJobDB.run_id == run_id))
        run_result = await session.execute(select(ParserRunDB).where(ParserRunDB.id == run_id))
        job = job_result.scalar_one()
        run = run_result.scalar_one()
        assert job.status == "dead_letter"
        assert job.attempt_count == 2
        assert run.status == "dead_letter"

    async with phase2_session_factory() as session:
        replayed = await parser_service.replay_dead_letter_parser_run_job(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
        )
    assert replayed is True

    async with phase2_session_factory() as session:
        job_result = await session.execute(select(ParserRunJobDB).where(ParserRunJobDB.run_id == run_id))
        run_result = await session.execute(select(ParserRunDB).where(ParserRunDB.id == run_id))
        job = job_result.scalar_one()
        run = run_result.scalar_one()
        assert job.status == "queued"
        assert job.attempt_count == 0
        assert run.status == "pending"

    async with phase2_session_factory() as session:
        second_replay = await parser_service.replay_dead_letter_parser_run_job(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
        )
    assert second_replay is True


def test_production_settings_fail_closed_for_operational_state():
    with pytest.raises(ValueError, match="REDIS_URL is required"):
        Settings(
            ALG_API_KEY="phase2-key",
            ENV="production",
            GOOGLE_CLIENT_ID="phase2.apps.googleusercontent.com",
            STATE_BACKEND="auto",
        )

    with pytest.raises(ValueError, match="STATE_BACKEND=memory is not allowed"):
        Settings(
            ALG_API_KEY="phase2-key",
            ENV="production",
            GOOGLE_CLIENT_ID="phase2.apps.googleusercontent.com",
            REDIS_URL="redis://localhost:6379/0",
            STATE_BACKEND="memory",
        )


@pytest.mark.asyncio
async def test_parse_async_endpoint_enqueues_durable_job(app_client, auth_headers, monkeypatch):
    import app_main

    now = datetime.utcnow()
    captured: dict[str, object] = {}

    async def _fake_create_parser_run(
        session,  # noqa: ARG001
        tenant_id: str,
        file_id: str,
        schema_id=None,
        extractor_id=None,
        classifier_id=None,
        splitter_id=None,
        metadata=None,
    ):
        return ParserRunStatus(
            run_id="run_phase2_async",
            file_id=file_id,
            status="pending",
            tenant_id=tenant_id,
            schema_id=schema_id,
            extractor_id=extractor_id,
            classifier_id=classifier_id,
            splitter_id=splitter_id,
            classification_result=None,
            split_chunks=None,
            extracted_data=None,
            confidence_score=None,
            started_at=None,
            completed_at=None,
            processing_time_ms=None,
            error_message=None,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )

    async def _fake_enqueue_parser_run_job(
        session,  # noqa: ARG001
        tenant_id: str,
        run_id: str,
        *,
        max_attempts: int = 5,
    ):
        captured["tenant_id"] = tenant_id
        captured["run_id"] = run_id
        captured["max_attempts"] = max_attempts
        return SimpleNamespace(id="pjob_test")

    monkeypatch.setattr(app_main.parser_service, "create_parser_run", _fake_create_parser_run)
    monkeypatch.setattr(app_main.parser_service, "enqueue_parser_run_job", _fake_enqueue_parser_run_job)

    response = await app_client.post(
        "/api/parse/async",
        headers=auth_headers,
        json={"file_id": "file_phase2_async"},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["run_id"] == "run_phase2_async"
    assert captured["run_id"] == "run_phase2_async"
    assert captured["tenant_id"] == auth_headers["X-Tenant-Id"]
    assert int(captured["max_attempts"]) >= 1


@pytest.mark.asyncio
async def test_parse_sync_endpoint_does_not_enqueue_async_job(app_client, auth_headers, monkeypatch):
    import app_main

    now = datetime.utcnow()

    async def _fake_create_parser_run(
        session,  # noqa: ARG001
        tenant_id: str,
        file_id: str,
        schema_id=None,
        extractor_id=None,
        classifier_id=None,
        splitter_id=None,
        metadata=None,
    ):
        return ParserRunStatus(
            run_id="run_phase2_sync",
            file_id=file_id,
            status="pending",
            tenant_id=tenant_id,
            schema_id=schema_id,
            extractor_id=extractor_id,
            classifier_id=classifier_id,
            splitter_id=splitter_id,
            classification_result=None,
            split_chunks=None,
            extracted_data=None,
            confidence_score=None,
            started_at=None,
            completed_at=None,
            processing_time_ms=None,
            error_message=None,
            created_at=now,
            updated_at=now,
            metadata=metadata,
        )

    async def _fake_execute_parser_run(session, tenant_id: str, run_id: str):  # noqa: ARG001
        return ParseResult(
            run_id=run_id,
            file_id="file_phase2_sync",
            status="completed",
            classification=None,
            chunks=None,
            extracted=None,
            confidence=None,
            processing_time_ms=1,
            completed_at=now,
            error=None,
        )

    async def _forbidden_enqueue(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("/parse should not enqueue async worker jobs")

    monkeypatch.setattr(app_main.parser_service, "create_parser_run", _fake_create_parser_run)
    monkeypatch.setattr(app_main.parser_service, "execute_parser_run", _fake_execute_parser_run)
    monkeypatch.setattr(app_main.parser_service, "enqueue_parser_run_job", _forbidden_enqueue)

    response = await app_client.post(
        "/api/parse",
        headers=auth_headers,
        json={"file_id": "file_phase2_sync"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "run_phase2_sync"
    assert data["status"] == "completed"


async def test_redis_rate_limit_store_close_uses_aclose_once():
    """close() uses aclose() (close() is deprecated in redis-py) and is safe to repeat."""

    class _Client:
        def __init__(self):
            self.calls = []

        async def aclose(self):
            self.calls.append("aclose")

        async def close(self):  # pragma: no cover - must not be called
            self.calls.append("close")

    store = RedisRateLimitStore("redis://127.0.0.1:6379/0")
    client = _Client()
    store._client = client

    await store.close()
    await store.close()

    assert client.calls == ["aclose"]
