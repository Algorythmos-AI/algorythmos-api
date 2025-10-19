import asyncio
import pytest


pytestmark = pytest.mark.asyncio


async def test_idempotency_same_key_same_run_id(app_client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "stage7-same"}
    payload = {"input_path": "tests/data/sample.pdf"}

    resp1 = await app_client.post("/processors/demo/runs", headers=headers, json=payload)
    resp2 = await app_client.post("/processors/demo/runs", headers=headers, json=payload)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]


async def test_idempotency_race_two_requests_same_key(app_client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "stage7-race"}
    payload = {"input_path": "tests/data/sample.pdf"}

    async def _post_once():
        return await app_client.post("/processors/demo/runs", headers=headers, json=payload)

    resp_one, resp_two = await asyncio.gather(_post_once(), _post_once())

    assert resp_one.status_code == 200
    assert resp_two.status_code == 200
    ids = {resp_one.json()["id"], resp_two.json()["id"]}
    assert len(ids) == 1
