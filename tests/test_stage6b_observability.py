import os
import time
from typing import Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure predictable env
os.environ.setdefault("ALG_API_KEY", "local_dummy")
os.environ.setdefault("VENDOR_WEBHOOK_SECRET", "stage6b-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_stage6b.db")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module

app = app_module.app

from app.database import engine
from app.models import Base
from config import settings


@pytest_asyncio.fixture(autouse=True)
async def reset_db(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from vendor_libs.utils.runstore import RunStore as _RunStore

    new_store = _RunStore()
    monkeypatch.setattr(app_module, "run_store", new_store, raising=False)
    monkeypatch.setattr("vendor_libs.utils.runstore.run_store", new_store, raising=False)
    app_module._processor_runs.clear()

    yield


@pytest_asyncio.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _maybe_get(client: AsyncClient, path: str):
    return client.get(path)


@pytest.mark.anyio
async def test_request_id_echo_and_generation(api_client):
    # server-generated id
    resp = await api_client.get("/version")
    if resp.status_code == 404:
        resp = await api_client.get("/api/version")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    auto_id = resp.headers["X-Request-ID"]
    assert len(auto_id) >= 8

    # client provided id
    resp2 = await api_client.get("/version", headers={"X-Request-ID": "abc-123"})
    if resp2.status_code == 404:
        resp2 = await api_client.get("/api/version", headers={"X-Request-ID": "abc-123"})
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Request-ID") == "abc-123"


@pytest.mark.anyio
async def test_metrics_collect_vendor_and_run_counters(api_client, monkeypatch):
    # Stub vendor upload + job creation to avoid network
    state: Dict[str, int] = {"uploads": 0, "jobs": 0}

    async def _fake_upload(files):
        state["uploads"] += 1
        return {"input_path": "vendor://stub"}

    async def _fake_job(input_path, payload, *, tenant_id=None):
        state["jobs"] += 1
        return {"job_id": f"job-{state['jobs']}"}

    monkeypatch.setattr("vendor_libs.services.vendor.upload_files_stream", _fake_upload)
    monkeypatch.setattr("vendor_libs.services.vendor.create_job", _fake_job)

    # Start a run to increment counters
    resp = await api_client.post(
        "/processors/demo/runs",
        headers={"X-Api-Key": settings.ALG_API_KEY, "X-Tenant-Id": "tenant-stage6b", "Idempotency-Key": "obs"},
        files={"files": ("doc.pdf", b"%PDF-1.4\n", "application/pdf")},
    )
    assert resp.status_code == 200

    # Trigger vendor health to ensure histogram has data (even if it fails)
    health = await api_client.get("/vendor/healthz")
    assert health.status_code in (204, 502)

    metrics_headers = {"X-Api-Key": settings.ALG_API_KEY}
    metrics = await api_client.get("/metrics", headers=metrics_headers)
    if metrics.status_code == 404:
        metrics = await api_client.get("/api/metrics", headers=metrics_headers)
    assert metrics.status_code == 200
    body = metrics.text

    assert "vendor_request_latency_seconds_bucket" in body
    assert "runs_started_total" in body
    assert "runs_succeeded_total" in body
    assert "runs_failed_total" in body
