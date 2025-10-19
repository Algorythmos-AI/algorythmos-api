import asyncio
import importlib.util
import hashlib
import hmac
import os
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
import respx
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ALG_API_KEY", "local_dummy")
os.environ.setdefault("VENDOR_WEBHOOK_SECRET", "stage7-secret")
os.environ.setdefault("NO_NETWORK", "1")

APP_MODULE_PATH = ROOT / "app.py"
spec = importlib.util.spec_from_file_location("app", APP_MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load app module from app.py")
app_module = importlib.util.module_from_spec(spec)
sys.modules["app"] = app_module
spec.loader.exec_module(app_module)

fastapi_app = app_module.app
WEBHOOK_REPLAY_TTL_S = app_module.WEBHOOK_REPLAY_TTL_S

from app.database import engine  # noqa: E402
from config import settings  # noqa: E402
from vendor_libs.services import vendor as vendor_services  # noqa: E402
from vendor_libs.utils import http as http_utils  # noqa: E402
from vendor_libs.utils.runstore import RunStore  # noqa: E402
from vendor_libs.utils.security import ReplaySet  # noqa: E402

TEST_VENDOR_BASE = "https://vendor.test"

settings.ALG_API_KEY = os.environ["ALG_API_KEY"]
settings.VENDOR_WEBHOOK_SECRET = os.environ["VENDOR_WEBHOOK_SECRET"]

RUNS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    processor TEXT NOT NULL,
    tenant_id TEXT,
    status TEXT NOT NULL,
    output JSON,
    error JSON,
    vendor_job_id TEXT UNIQUE,
    idempotency_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
"""

RUNS_IDEM_UNIQUE = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_tenant_proc_idem
ON runs (tenant_id, processor, idempotency_key)
WHERE idempotency_key IS NOT NULL;
"""

RUNS_IDEM_INDEX = """
CREATE INDEX IF NOT EXISTS ix_runs_idempotency_key
ON runs (idempotency_key);
"""


@pytest_asyncio.fixture(autouse=True)
async def reset_state(monkeypatch):
    """Reset database and in-memory caches between tests."""
    await http_utils.close_http_client()

    async with engine.begin() as conn:
        await conn.exec_driver_sql("DROP TABLE IF EXISTS runs")
        await conn.exec_driver_sql(RUNS_TABLE_DDL)
        await conn.exec_driver_sql(RUNS_IDEM_UNIQUE)
        await conn.exec_driver_sql(RUNS_IDEM_INDEX)

    new_store = RunStore()
    monkeypatch.setattr("vendor_libs.utils.runstore.run_store", new_store, raising=False)
    monkeypatch.setattr(app_module, "run_store", new_store, raising=False)
    app_module._processor_runs.clear()

    new_replay = ReplaySet(ttl_seconds=WEBHOOK_REPLAY_TTL_S)
    monkeypatch.setattr(app_module, "webhook_replay_set", new_replay, raising=False)

    yield


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """Guard against accidental real network usage."""
    monkeypatch.setenv("NO_NETWORK", "1")


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {
        "X-Api-Key": settings.ALG_API_KEY,
        "X-Tenant-Id": "tenant-stage7",
    }


@pytest.fixture
def fast_sleep(monkeypatch):
    """Monkeypatch asyncio.sleep to capture backoff durations without waiting."""
    calls: dict[str, list[float]] = {"durations": []}

    async def _sleep(delay: float, *args, **kwargs):
        calls["durations"].append(float(delay))
        return None

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    return calls


@pytest.fixture
def fake_vendor(monkeypatch):
    """respx router for intercepting all vendor traffic at TEST_VENDOR_BASE."""
    monkeypatch.setattr(vendor_services.vendor_service, "base_url", TEST_VENDOR_BASE, raising=False)
    monkeypatch.setenv("API_BASE", TEST_VENDOR_BASE)

    with respx.mock(assert_all_mocked=False, assert_all_called=False) as router:
        yield router


@pytest_asyncio.fixture
async def app_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def sign_v1():
    """Generate a v1 signature header for webhook payloads."""
    secret = settings.VENDOR_WEBHOOK_SECRET.encode("utf-8")

    def _sign(body_bytes: bytes, *, timestamp: int | None = None) -> str:
        ts = int(time.time()) if timestamp is None else timestamp
        digest = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
        return f"v1,t={ts},sig={digest}"

    return _sign


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Force AnyIO-backed tests to run with asyncio backend only."""
    return "asyncio"
