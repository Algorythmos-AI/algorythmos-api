import hashlib
import hmac
import json
import os
import time
from typing import Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ALG_API_KEY", "local_dummy")
os.environ.setdefault("VENDOR_WEBHOOK_SECRET", "stage5-secret")

import app as app_module
from app import WEBHOOK_REPLAY_TTL_S, WEBHOOK_REPLAY_WINDOW_S, app as fastapi_app
from config import settings
from vendor_libs.utils.runstore import RunStore
from vendor_libs.utils.security import ReplaySet

settings.VENDOR_WEBHOOK_SECRET = os.environ["VENDOR_WEBHOOK_SECRET"]


def hmac_hex(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def v1_header(secret: str, raw: bytes, *, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    return f"v1,t={ts},sig={hmac_hex(secret, raw)}"


def legacy_header(secret: str, raw: bytes) -> str:
    return "sha256=" + hmac_hex(secret, raw)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    new_store = RunStore()
    monkeypatch.setattr(app_module, "run_store", new_store, raising=False)
    monkeypatch.setattr("vendor_libs.utils.runstore.run_store", new_store, raising=False)
    app_module._processor_runs.clear()

    new_replay = ReplaySet(ttl_seconds=WEBHOOK_REPLAY_TTL_S)
    monkeypatch.setattr(app_module, "webhook_replay_set", new_replay, raising=False)
    yield


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    return {
        "X-Api-Key": settings.ALG_API_KEY,
        "X-Tenant-Id": "tenant-stage5",
    }


@pytest_asyncio.fixture
async def api_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _link_run(job_id: str) -> str:
    run_id = f"run-{job_id}"
    snapshot = {
        "id": run_id,
        "run_id": run_id,
        "processor": "demo",
        "processor_name": "demo",
        "tenant_id": "tenant-stage5",
        "status": "queued",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "vendor_job_id": job_id,
    }
    app_module.run_store.put_run(run_id, snapshot)
    app_module.run_store.link_vendor_job(job_id, run_id)
    app_module._processor_runs[run_id] = dict(snapshot)
    return run_id


@pytest.mark.asyncio
async def test_v1_signature_updates_run(api_client, auth_headers):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-v1"
    run_id = _link_run(job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {"ok": True}}
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": v1_header(secret, raw),
        "X-Vendor-Event-ID": "evt-v1",
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204

    result = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "succeeded"
    assert data["output"]["ok"] is True


@pytest.mark.asyncio
async def test_bad_signature_returns_401(api_client):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-badsig"
    _link_run(job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode()
    sig = v1_header(secret, raw)
    bad_sig = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": bad_sig,
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_timestamp_outside_window_rejected(api_client):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-old"
    _link_run(job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode()
    ts = int(time.time()) - (WEBHOOK_REPLAY_WINDOW_S + 10)
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": v1_header(secret, raw, timestamp=ts),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_replay_returns_204(api_client, auth_headers):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-replay"
    run_id = _link_run(job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {"seen": True}}
    raw = json.dumps(body, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": v1_header(secret, raw),
        "X-Vendor-Event-ID": "evt-replay",
    }

    first = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert first.status_code == 204
    second = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert second.status_code == 204

    result = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["status"] == "succeeded"


@pytest.mark.asyncio
async def test_unknown_job_returns_204(api_client):
    secret = settings.VENDOR_WEBHOOK_SECRET

    body = {"job_id": "job-unknown", "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": v1_header(secret, raw),
        "X-Vendor-Event-ID": "evt-unknown",
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_legacy_with_timestamp_allowed(api_client, auth_headers):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-legacy"
    run_id = _link_run(job_id)

    body = {"job_id": job_id, "status": "failed", "error": {"msg": "oops"}}
    raw = json.dumps(body).encode()
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": legacy_header(secret, raw),
        "X-Vendor-Timestamp": str(ts),
        "X-Vendor-Event-ID": "evt-legacy",
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204

    result = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "failed"
    assert data["error"]["msg"] == "oops"


@pytest.mark.asyncio
async def test_legacy_without_timestamp_rejected(api_client):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-legacy-miss"
    _link_run(job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": legacy_header(secret, raw),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_content_type_returns_415(api_client):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-content"
    _link_run(job_id)

    body = {"job_id": job_id, "status": "succeeded", "output": {}}
    raw = json.dumps(body).encode()
    headers = {
        "Content-Type": "text/plain",
        "X-Vendor-Signature": v1_header(secret, raw),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_malformed_json_returns_400(api_client):
    secret = settings.VENDOR_WEBHOOK_SECRET
    job_id = "job-bad-json"
    _link_run(job_id)

    raw = b"{invalid json]"
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": v1_header(secret, raw),
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 400
