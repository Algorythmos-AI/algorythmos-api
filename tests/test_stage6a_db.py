import asyncio
import json
import os
import time
from typing import Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_stage6a.db")
os.environ.setdefault("VENDOR_WEBHOOK_SECRET", "stage6a-secret")
os.environ.setdefault("ALG_API_KEY", "local_dummy")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module

app = app_module.app

from app.database import engine
from app.models import Base, Run
from config import settings
from vendor_libs.utils.runstore import RunStore

settings.VENDOR_WEBHOOK_SECRET = os.environ["VENDOR_WEBHOOK_SECRET"]


def _hmac_v1(secret: str, raw: bytes, *, timestamp: int | None = None) -> str:
    import hmac
    import hashlib

    ts = int(time.time()) if timestamp is None else timestamp
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return f"v1,t={ts},sig={sig}"


@pytest.fixture(autouse=True)
async def reset_db(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    new_store = RunStore()
    monkeypatch.setattr("vendor_libs.utils.runstore.run_store", new_store, raising=False)
    monkeypatch.setattr(app_module, "run_store", new_store, raising=False)
    app_module._processor_runs.clear()

    yield


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    return {
        "X-Api-Key": settings.ALG_API_KEY,
        "X-Tenant-Id": "tenant-stage6a",
    }


@pytest.fixture
def vendor_stub(monkeypatch):
    state = {"uploads": 0, "jobs": 0}

    async def _fake_upload(files):
        state["uploads"] += 1
        return {"input_path": "vendor://mock"}

    async def _fake_create_job(input_path, payload, *, tenant_id=None):
        state["jobs"] += 1
        return {"job_id": f"job-{state['jobs']}"}

    monkeypatch.setattr("vendor_libs.services.vendor.upload_files_stream", _fake_upload)
    monkeypatch.setattr("vendor_libs.services.vendor.create_job", _fake_create_job)
    return state


@pytest_asyncio.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _pdf_file(name: str = "doc.pdf"):
    return {"files": (name, b"%PDF-1.4\n", "application/pdf")}


async def _fetch_run(run_id: str) -> Run | None:
    from app.database import async_session_factory

    async with async_session_factory() as session:
        return await session.get(Run, run_id)


@pytest.mark.asyncio
async def test_idempotent_run_reuses_existing(api_client, auth_headers, vendor_stub):
    headers = {**auth_headers, "Idempotency-Key": "idem-1"}

    resp1 = await api_client.post("/processors/demo/runs", headers=headers, files=_pdf_file())
    assert resp1.status_code == 200
    data1 = resp1.json()

    resp2 = await api_client.post("/processors/demo/runs", headers=headers, files=_pdf_file("doc2.pdf"))
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data1["id"] == data2["id"]
    assert vendor_stub["uploads"] == 1
    assert vendor_stub["jobs"] == 1


@pytest.mark.asyncio
async def test_concurrent_idempotent_requests(api_client, auth_headers, vendor_stub):
    headers = {**auth_headers, "Idempotency-Key": "idem-concurrent"}

    async def _post():
        return await api_client.post("/processors/demo/runs", headers=headers, files=_pdf_file())

    resp_one, resp_two = await asyncio.gather(_post(), _post())
    assert resp_one.status_code == 200
    assert resp_two.status_code == 200
    ids = {resp_one.json()["id"], resp_two.json()["id"]}
    assert len(ids) == 1
    assert vendor_stub["uploads"] == 1
    assert vendor_stub["jobs"] == 1


@pytest.mark.asyncio
async def test_webhook_updates_persisted_run(api_client, auth_headers, vendor_stub):
    headers = {**auth_headers, "Idempotency-Key": "idem-hook"}

    create_resp = await api_client.post("/processors/demo/runs", headers=headers, files=_pdf_file())
    assert create_resp.status_code == 200
    run_id = create_resp.json()["id"]

    run = await _fetch_run(run_id)
    assert run is not None
    job_id = run.vendor_job_id
    assert job_id

    payload = {"job_id": job_id, "status": "succeeded", "output": {"ok": True}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = _hmac_v1(settings.VENDOR_WEBHOOK_SECRET, raw)
    webhook_headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": sig,
        "X-Vendor-Event-ID": "evt-success",
    }

    webhook_resp = await api_client.post("/webhooks/vendor", headers=webhook_headers, content=raw)
    assert webhook_resp.status_code == 204

    get_resp = await api_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["status"] == "succeeded"
    assert data["output"]["ok"] is True


@pytest.mark.asyncio
async def test_unknown_job_webhook_is_noop(api_client):
    payload = {"job_id": "missing", "status": "succeeded", "output": {}}
    raw = json.dumps(payload).encode()
    sig = _hmac_v1(settings.VENDOR_WEBHOOK_SECRET, raw)
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": sig,
        "X-Vendor-Event-ID": "evt-missing",
    }

    resp = await api_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204
