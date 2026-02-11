import io
import os
from typing import Dict

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ALG_API_KEY", "local_dummy")

from app import RUN_MAX_FILE_BYTES, RUN_MAX_FILES, app  # noqa: E402
from config import settings  # noqa: E402

settings.VENDOR_WEBHOOK_SECRET = "stage4-secret"


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    return {
        "X-Api-Key": settings.ALG_API_KEY,
        "X-Tenant-Id": "tenant-stage4",
    }


@pytest_asyncio.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_valid_upload_triggers_vendor_calls(api_client, auth_headers):
    job_id = "job-upload"
    async with respx.mock(base_url="https://api.vendor.example", assert_all_called=False) as router:
        upload_route = router.post("/extract/upload").mock(
            return_value=httpx.Response(200, json={"input_path": "s3://uploads/file.pdf"})
        )
        job_route = router.post("/jobs").mock(
            return_value=httpx.Response(200, json={"job_id": job_id})
        )

        resp = await api_client.post(
            "/processors/demo/runs",
            headers=auth_headers,
            files={"files": ("doc.pdf", b"%PDF-1.4\n", "application/pdf")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["vendor_job_id"] == job_id
    assert upload_route.called
    assert job_route.called


@pytest.mark.asyncio
async def test_too_many_files_rejected_stage4(api_client, auth_headers):
    files = [
        ("files", (f"doc_{idx}.pdf", b"%PDF-1.4\n", "application/pdf"))
        for idx in range(RUN_MAX_FILES + 1)
    ]

    async with respx.mock(base_url="https://api.vendor.example", assert_all_called=False) as router:
        router.post("/extract/upload").mock(return_value=httpx.Response(200, json={}))
        router.post("/jobs").mock(return_value=httpx.Response(200, json={"job_id": "unused"}))

        resp = await api_client.post(
            "/processors/demo/runs",
            headers=auth_headers,
            files=files,
        )

    assert resp.status_code == 400
    assert len(router.calls) == 0


@pytest.mark.asyncio
async def test_bad_mime_rejected_stage4(api_client, auth_headers):
    async with respx.mock(base_url="https://api.vendor.example", assert_all_called=False) as router:
        router.post("/extract/upload").mock(return_value=httpx.Response(200, json={}))
        router.post("/jobs").mock(return_value=httpx.Response(200, json={"job_id": "unused"}))

        resp = await api_client.post(
            "/processors/demo/runs",
            headers=auth_headers,
            files={"files": ("notes.txt", b"hello", "text/plain")},
        )

    assert resp.status_code == 415
    assert len(router.calls) == 0


@pytest.mark.asyncio
async def test_large_file_rejected_stage4(api_client, auth_headers):
    oversized = io.BytesIO(b"x" * (RUN_MAX_FILE_BYTES + 1))

    async with respx.mock(base_url="https://api.vendor.example", assert_all_called=False) as router:
        upload_route = router.post("/extract/upload").mock(return_value=httpx.Response(200, json={}))
        job_route = router.post("/jobs").mock(return_value=httpx.Response(200, json={"job_id": "unused"}))

        resp = await api_client.post(
            "/processors/demo/runs",
            headers=auth_headers,
            files={"files": ("huge.pdf", oversized, "application/pdf")},
        )

    assert resp.status_code == 413
    assert not job_route.called
