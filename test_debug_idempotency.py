import asyncio
import pytest
import sys
import os
from pathlib import Path

# Set up environment like conftest does
os.environ.setdefault("ALG_API_KEY", "local_dummy")
os.environ.setdefault("VENDOR_WEBHOOK_SECRET", "stage7-secret")
os.environ.setdefault("NO_NETWORK", "1")

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from httpx import AsyncClient, ASGITransport
from app import app
from config import settings

async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "X-Api-Key": settings.ALG_API_KEY,
            "X-Tenant-Id": "tenant-stage7",
            "Idempotency-Key": "test123",
        }
        payload = {"input_path": "tests/data/sample.pdf"}
        resp = await client.post("/processors/demo/runs", headers=headers, json=payload)
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.json()}")

asyncio.run(main())
