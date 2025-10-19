import hashlib
import hmac
import json
import time

import pytest

from app.database import async_session_factory
from app.models import Run
from config import settings


pytestmark = pytest.mark.asyncio


async def test_webhook_v1_good_signature_and_replay(app_client, auth_headers, sign_v1):
    job_id = "job-webhook-1"
    run_id = "run-webhook-1"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                processor="demo",
                tenant_id=auth_headers["X-Tenant-Id"],
                status="queued",
                vendor_job_id=job_id,
            )
        )
        await session.commit()

    payload = {"job_id": job_id, "status": "succeeded", "output": {"ok": True}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signature = sign_v1(raw, timestamp=timestamp)
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": signature,
        "X-Vendor-Event-ID": "evt-webhook-1",
    }

    first = await app_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert first.status_code == 204

    run_resp = await app_client.get(f"/processors/demo/runs/{run_id}", headers=auth_headers)
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["status"] == "succeeded"
    assert data["output"]["ok"] is True

    second = await app_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert second.status_code == 204


async def test_webhook_legacy_missing_timestamp_unauthorized(app_client):
    payload = {"job_id": "legacy-job", "status": "failed", "error": {"code": "X"}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(settings.VENDOR_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": f"sha256={digest}",
    }

    resp = await app_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 401


async def test_webhook_unknown_job_noop(app_client, sign_v1):
    payload = {"job_id": "job-missing", "status": "succeeded", "output": {}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = sign_v1(raw)
    headers = {
        "Content-Type": "application/json",
        "X-Vendor-Signature": signature,
        "X-Vendor-Event-ID": "evt-missing",
    }

    resp = await app_client.post("/webhooks/vendor", headers=headers, content=raw)
    assert resp.status_code == 204
