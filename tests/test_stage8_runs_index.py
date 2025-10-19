import datetime as dt
from typing import List

import pytest
from httpx import AsyncClient
from sqlalchemy import insert

from app import app
from app.database import async_session_factory
from app.models import Run

pytestmark = pytest.mark.anyio


async def _seed_runs(*, processor: str = "demo", tenant: str = "tenant-stage7", status: str = "queued", count: int = 5, offset: int = 0) -> List[str]:
    """Seed runs for pagination tests. Returns inserted ids."""
    now = dt.datetime.now(dt.timezone.utc)
    ids: List[str] = []
    async with async_session_factory() as session:
        for idx in range(count):
            run_id = f"run_{processor}_{status}_{offset + idx}"
            created_at = now - dt.timedelta(seconds=offset + idx)
            await session.execute(
                insert(Run).values(
                    id=run_id,
                    processor=processor,
                    tenant_id=tenant,
                    status=status,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            ids.append(run_id)
        await session.commit()
    return ids


async def test_list_runs_pagination(app_client, auth_headers):
    tenant = auth_headers["X-Tenant-Id"]
    await _seed_runs(tenant=tenant, count=6)

    resp1 = await app_client.get(
        "/processors/demo/runs",
        params={"limit": 3},
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1["items"]) == 3
    assert page1["next_cursor"]

    resp2 = await app_client.get(
        "/processors/demo/runs",
        params={"limit": 3, "cursor": page1["next_cursor"]},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    page2 = resp2.json()

    combined = page1["items"] + page2["items"]
    ids = [item["id"] for item in combined]
    assert len(ids) == 6
    assert len(set(ids)) == 6

    # Verify ordering is newest first within each page
    for page in (page1["items"], page2["items"]):
        created = [item["created_at"] for item in page]
        assert created == sorted(created, reverse=True)
        assert all("has_output" in item and "has_error" in item for item in page)

    # Ensure keyset boundary works (last item of first page >= first item of second page)
    assert page1["items"][-1]["created_at"] >= page2["items"][0]["created_at"]


async def test_list_runs_filter_status(app_client, auth_headers):
    tenant = auth_headers["X-Tenant-Id"]
    await _seed_runs(tenant=tenant, status="queued", count=2)
    await _seed_runs(tenant=tenant, status="succeeded", count=3, offset=10)

    resp = await app_client.get(
        "/processors/demo/runs",
        params={"status": "succeeded"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    assert all(item["status"] == "succeeded" for item in data["items"])

    bad = await app_client.get(
        "/processors/demo/runs",
        params={"status": "unknown"},
        headers=auth_headers,
    )
    assert bad.status_code == 400
    body = bad.json()
    assert body["detail"]["code"] == "INVALID_STATUS"
