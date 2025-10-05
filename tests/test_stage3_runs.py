import io
import os
from typing import Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ALG_API_KEY", "local_dummy")

from app import RUN_MAX_FILE_BYTES, RUN_MAX_FILES, app  # noqa: E402
from config import settings  # noqa: E402
from vendor_libs.services import vendor  # noqa: E402


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    return {
        "X-Api-Key": settings.ALG_API_KEY,
        "X-Tenant-Id": "tenant-stage3",
    }


@pytest.fixture
def vendor_upload_stub(monkeypatch):
    state = {"calls": 0, "job_calls": 0}

    async def _fake_upload(files):
        state["calls"] += 1
        return {"ok": True, "count": len(files), "input_path": "mock://upload"}

    async def _fake_create_job(input_path, payload, *, tenant_id=None):
        state["job_calls"] += 1
        return {"job_id": f"job-{state['job_calls']}"}

    monkeypatch.setattr(vendor, "upload_files_stream", _fake_upload)
    monkeypatch.setattr(vendor, "create_job", _fake_create_job)
    return state


@pytest_asyncio.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _pdf_file(content: bytes = b"%PDF-1.4\n", name: str = "sample.pdf") -> Dict[str, tuple[str, bytes, str]]:
    return {"files": (name, content, "application/pdf")}


def _unwrap_detail(payload: Dict[str, object]) -> Dict[str, object]:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return detail
    return payload


@pytest.mark.asyncio
async def test_idempotency_key_returns_same_run_id(api_client, auth_headers, vendor_upload_stub):
    headers = {**auth_headers, "Idempotency-Key": "stage3-key"}

    resp1 = await api_client.post("/processors/demo/runs", headers=headers, files=_pdf_file())
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "queued"

    resp2 = await api_client.post("/processors/demo/runs", headers=headers, files=_pdf_file())
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data1["id"] == data2["id"]
    assert vendor_upload_stub["calls"] == 1
    assert vendor_upload_stub["job_calls"] == 1


@pytest.mark.asyncio
async def test_too_many_files_rejected(api_client, auth_headers, vendor_upload_stub):
    files = [
        ("files", (f"doc_{idx}.pdf", b"%PDF-1.4\n", "application/pdf"))
        for idx in range(RUN_MAX_FILES + 1)
    ]
    resp = await api_client.post("/processors/demo/runs", headers=auth_headers, files=files)
    assert resp.status_code == 400
    detail = _unwrap_detail(resp.json())
    assert detail.get("code") == "TOO_MANY_FILES"
    assert "Too many files" in detail.get("message", "")
    assert vendor_upload_stub["calls"] == 0
    assert vendor_upload_stub["job_calls"] == 0


@pytest.mark.asyncio
async def test_bad_mime_rejected(api_client, auth_headers, vendor_upload_stub):
    files = {"files": ("notes.txt", b"hello", "text/plain")}
    resp = await api_client.post("/processors/demo/runs", headers=auth_headers, files=files)
    assert resp.status_code == 415
    detail = _unwrap_detail(resp.json())
    assert detail.get("code") == "UNSUPPORTED_MEDIA_TYPE"
    assert "Unsupported content type" in detail.get("message", "")
    assert vendor_upload_stub["calls"] == 0
    assert vendor_upload_stub["job_calls"] == 0


@pytest.mark.asyncio
async def test_oversized_rejected(api_client, auth_headers, vendor_upload_stub):
    oversized = io.BytesIO(b"x" * (RUN_MAX_FILE_BYTES + 1))
    files = {"files": ("huge.pdf", oversized, "application/pdf")}
    resp = await api_client.post("/processors/demo/runs", headers=auth_headers, files=files)
    assert resp.status_code == 413
    detail = _unwrap_detail(resp.json())
    assert detail.get("code") == "FILE_TOO_LARGE"
    assert "exceeds" in detail.get("message", "")
    assert vendor_upload_stub["calls"] == 0
    assert vendor_upload_stub["job_calls"] == 0
