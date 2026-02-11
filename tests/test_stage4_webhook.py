import hashlib
import hmac
import json
import os
from typing import Dict

import httpx
import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ALG_API_KEY", "local_dummy")

from app import app  # noqa: E402
from config import settings  # noqa: E402

settings.VENDOR_WEBHOOK_SECRET = "stage4-secret"


def _signature(raw: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


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


async def _create_run(api_client, auth_headers, job_id: str = "job-123") -> str:
    async with respx.mock(base_url="https://api.vendor.example") as router:
        router.post("/extract/upload").mock(
            return_value=httpx.Response(200, json={"input_path": f"s3://uploads/{job_id}.pdf"})
        )
        router.post("/jobs").mock(
            return_value=httpx.Response(200, json={"job_id": job_id})
        )
        resp = await api_client.post(
            "/processors/demo/runs",
            headers=auth_headers,
            files={"files": ("doc.pdf", b"%PDF-1.4\n", "application/pdf")},
        )
    assert resp.status_code == 200
    data = resp.json()
    return data["id"]


@pytest.mark.asyncio
async def test_webhook_happy_path_updates_run(api_client, auth_headers):
    job_id = "job-happy"
    run_id = await _create_run(api_client, auth_headers, job_id=job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {"ok": True, "value": 1}}
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": _signature(raw, settings.VENDOR_WEBHOOK_SECRET),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204

    result = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "succeeded"
    assert data["output"]["value"] == 1


@pytest.mark.asyncio
async def test_webhook_bad_signature_returns_401(api_client, auth_headers):
    job_id = "job-badsig"
    await _create_run(api_client, auth_headers, job_id=job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": "sha256=invalid",
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_replay_is_idempotent(api_client, auth_headers):
    job_id = "job-replay"
    run_id = await _create_run(api_client, auth_headers, job_id=job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {"seen": True}}
    raw = json.dumps(body).encode("utf-8")
    signature = _signature(raw, settings.VENDOR_WEBHOOK_SECRET)
    headers = {"Content-Type": "application/json", "X-Vendor-Signature": signature}

    first = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    second = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert first.status_code == 204
    assert second.status_code == 204

    result = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_webhook_unknown_job_id_is_noop(api_client, auth_headers):
    body = {"job_id": "unknown-job", "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": _signature(raw, settings.VENDOR_WEBHOOK_SECRET),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_webhook_failed_status_sets_error(api_client, auth_headers):
    job_id = "job-failed"
    run_id = await _create_run(api_client, auth_headers, job_id=job_id)

    body = {"job_id": job_id, "status": "failed", "error": {"message": "bad"}}
    raw = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": _signature(raw, settings.VENDOR_WEBHOOK_SECRET),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204

    result = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "failed"
    assert data["error"]["message"] == "bad"
