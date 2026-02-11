"""Phase 0 regression tests for parser orchestration and DB session wiring."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from document_processing.schemas import FileUpload, ParseResult, ParserRunStatus
from document_processing.services import parser_service


@pytest.mark.asyncio
async def test_execute_parser_run_calls_services_with_correct_argument_order(monkeypatch):
    """Parser orchestration should call downstream services with stable signatures."""

    run_db = SimpleNamespace(
        id="run_123",
        tenant_id="tenant_1",
        file_id="file_1",
        status="pending",
        schema_id="schema_1",
        extractor_id="extractor_1",
        classifier_id="classifier_1",
        splitter_id="splitter_1",
        classification_result=None,
        split_chunks=None,
        extracted_data=None,
        confidence_score=None,
        started_at=None,
        completed_at=None,
        processing_time_ms=None,
        updated_at=None,
        run_metadata={},
        error_message=None,
    )
    file_db = SimpleNamespace(
        id="file_1",
        filename="input.txt",
        content_type="text/plain",
    )

    class _Result:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Session:
        async def execute(self, _query):
            return _Result(run_db)

        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    session = _Session()
    calls: dict[str, tuple] = {}

    async def _fake_get_file(session_arg, tenant_id, file_id):
        assert session_arg is session
        assert tenant_id == "tenant_1"
        assert file_id == "file_1"
        return file_db

    async def _fake_get_file_content(file_obj):
        assert file_obj is file_db
        return b"hello world"

    async def _fake_classify(db, tenant_id, text, classifier_id=None):
        calls["classify"] = (db, tenant_id, text, classifier_id)
        return {"top_category": "invoice"}

    async def _fake_split(db, tenant_id, text, splitter_id=None):
        calls["split"] = (db, tenant_id, text, splitter_id)
        return {"chunks": []}

    async def _fake_extract(db, tenant_id, schema_id, text, extractor_id=None):
        calls["extract"] = (db, tenant_id, schema_id, text, extractor_id)
        return {"fields": [], "citations": [], "confidence": 0.95}

    monkeypatch.setattr(parser_service.file_service, "get_file", _fake_get_file)
    monkeypatch.setattr(parser_service.file_service, "get_file_content", _fake_get_file_content)
    monkeypatch.setattr(parser_service.format_detector, "extract_text", lambda *_args, **_kwargs: "hello world")
    monkeypatch.setattr(parser_service.format_detector, "extract_metadata", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(parser_service, "classify_document", _fake_classify)
    monkeypatch.setattr(parser_service, "split_document", _fake_split)
    monkeypatch.setattr(parser_service, "extract_with_schema", _fake_extract)

    result = await parser_service.execute_parser_run(session, "tenant_1", "run_123")

    assert result.status == "completed"
    assert calls["classify"] == (session, "tenant_1", "hello world", "classifier_1")
    assert calls["split"] == (session, "tenant_1", "hello world", "splitter_1")
    assert calls["extract"] == (session, "tenant_1", "schema_1", "hello world", "extractor_1")


async def _post_with_api_prefix_fallback(app_client, path: str, **kwargs):
    response = await app_client.post(path, **kwargs)
    if response.status_code == 404 and not path.startswith("/api/"):
        return await app_client.post(f"/api{path}", **kwargs)
    return response


@pytest.fixture
def override_db_session_dependency():
    """Override get_session dependency with a controlled sentinel session."""
    import app_main

    sentinel_session = object()

    async def _override_session():
        yield sentinel_session

    app_main.app.dependency_overrides[app_main.get_session] = _override_session
    # If any endpoint still touches app.state.db_session, this should fail loudly.
    app_main.app.state.db_session = None

    try:
        yield sentinel_session
    finally:
        app_main.app.dependency_overrides.pop(app_main.get_session, None)


@pytest.mark.asyncio
async def test_files_upload_uses_dependency_injected_session(
    app_client,
    auth_headers,
    monkeypatch,
    override_db_session_dependency,
):
    """Upload endpoint should use dependency-injected DB session, not app.state.db_session."""
    import app_main

    sentinel_session = override_db_session_dependency
    now = datetime.utcnow()

    async def _fake_upload_file(session, tenant_id, file, metadata):
        assert session is sentinel_session
        assert tenant_id == auth_headers["X-Tenant-Id"]
        return FileUpload(
            file_id="file_test_1",
            filename=file.filename or "upload.txt",
            content_type=file.content_type or "text/plain",
            size_bytes=11,
            checksum="abc123",
            tenant_id=tenant_id,
            created_at=now,
            metadata=metadata,
        )

    monkeypatch.setattr(app_main.file_service, "upload_file", _fake_upload_file)

    response = await _post_with_api_prefix_fallback(
        app_client,
        "/files",
        headers=auth_headers,
        files={"file": ("upload.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["file_id"] == "file_test_1"


@pytest.mark.asyncio
async def test_parse_sync_uses_dependency_injected_session(
    app_client,
    auth_headers,
    monkeypatch,
    override_db_session_dependency,
):
    """Parse endpoint should use dependency-injected DB session, not app.state.db_session."""
    import app_main

    sentinel_session = override_db_session_dependency
    now = datetime.utcnow()

    async def _fake_create_parser_run(
        session,
        tenant_id,
        file_id,
        schema_id=None,
        extractor_id=None,
        classifier_id=None,
        splitter_id=None,
        metadata=None,
    ):
        assert session is sentinel_session
        return ParserRunStatus(
            run_id="run_test_1",
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

    async def _fake_execute_parser_run(session, tenant_id, run_id):
        assert session is sentinel_session
        assert run_id == "run_test_1"
        return ParseResult(
            run_id=run_id,
            file_id="file_test_1",
            status="completed",
            classification=None,
            chunks=None,
            extracted=None,
            confidence=None,
            processing_time_ms=1,
            completed_at=now,
            error=None,
        )

    monkeypatch.setattr(app_main.parser_service, "create_parser_run", _fake_create_parser_run)
    monkeypatch.setattr(app_main.parser_service, "execute_parser_run", _fake_execute_parser_run)

    response = await _post_with_api_prefix_fallback(
        app_client,
        "/parse",
        headers=auth_headers,
        json={"file_id": "file_test_1"},
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == "run_test_1"
