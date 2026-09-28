import asyncio
import hashlib
import hmac
import importlib
import os
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
pytest_plugins = ("pytest_asyncio",)
import respx
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("ALG_API_KEY", "local_dummy")
os.environ.setdefault("VENDOR_WEBHOOK_SECRET", "stage7-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("NO_NETWORK", "1")
# Server-side path extraction is confined to this directory in tests (pytest's
# tmp dirs live under it); unset in deployed environments, so the feature is off.
import tempfile  # noqa: E402

# Tests exercise CORS from a local dev origin; production refuses local origins.
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("LOCAL_EXTRACT_BASE_DIR", str(Path(tempfile.gettempdir()).resolve()))

app_package = importlib.import_module("app")
app_module = getattr(app_package, "_app_entry", None)
if app_module is None:
    raise RuntimeError("Unable to resolve canonical app.py module from app package")
sys.modules["app_main"] = app_module

fastapi_app = app_package.app
# Default TTL for replay protection (used in Stage 5+ tests)
WEBHOOK_REPLAY_TTL_S = getattr(app_module, "WEBHOOK_REPLAY_TTL_S", 300)

from config import settings  # noqa: E402

# Import additional modules only if needed (for non-smoke tests)
try:
    from app.database import engine  # noqa: E402
    from vendor_libs.services import vendor as vendor_services  # noqa: E402
    from vendor_libs.utils import http as http_utils  # noqa: E402
    from vendor_libs.utils.runstore import RunStore  # noqa: E402
    from vendor_libs.utils.security import ReplaySet  # noqa: E402
except (ImportError, ModuleNotFoundError):
    # For smoke tests that don't need database/vendor modules
    engine = None
    vendor_services = None
    http_utils = None
    RunStore = None
    ReplaySet = None

TEST_VENDOR_BASE = "https://vendor.test"

settings.ALG_API_KEY = os.environ["ALG_API_KEY"]
settings.VENDOR_WEBHOOK_SECRET = os.environ["VENDOR_WEBHOOK_SECRET"]
settings.GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]

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
    if http_utils:
        await http_utils.close_http_client()

    if engine:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("DROP TABLE IF EXISTS runs")
            await conn.exec_driver_sql(RUNS_TABLE_DDL)
            await conn.exec_driver_sql(RUNS_IDEM_UNIQUE)
            await conn.exec_driver_sql(RUNS_IDEM_INDEX)

    if RunStore:
        new_store = RunStore()
        monkeypatch.setattr("vendor_libs.utils.runstore.run_store", new_store, raising=False)
        monkeypatch.setattr(app_module, "run_store", new_store, raising=False)
    
    if hasattr(app_module, "_processor_runs"):
        app_module._processor_runs.clear()

    if ReplaySet:
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
    if vendor_services:
        monkeypatch.setattr(vendor_services.vendor_service, "base_url", TEST_VENDOR_BASE, raising=False)
    monkeypatch.setenv("API_BASE", TEST_VENDOR_BASE)

    with respx.mock(assert_all_mocked=False, assert_all_called=False) as router:
        yield router


@pytest_asyncio.fixture
async def app_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest_asyncio.fixture
async def client(app_client: AsyncClient):
    """Backward-compatible alias for tests that still request `client`."""
    yield app_client


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


# --- Legacy failure ratchet -------------------------------------------------
# tests/known_failures.txt lists tests that were already failing on main when
# CI gating was restored. They run as non-strict xfail: CI stays green for the
# rest of the suite, a newly broken test still fails the build, and a repaired
# test shows up as XPASS so its line can be deleted. The list only shrinks.
_KNOWN_FAILURES_FILE = Path(__file__).with_name("known_failures.txt")


def _load_known_failures() -> set[str]:
    if not _KNOWN_FAILURES_FILE.exists():
        return set()
    return {
        line.strip()
        for line in _KNOWN_FAILURES_FILE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def pytest_collection_modifyitems(config, items):
    known = _load_known_failures()
    if not known:
        return
    marker = pytest.mark.xfail(
        reason="pre-existing failure on main; see tests/known_failures.txt",
        strict=False,
    )
    for item in items:
        if item.nodeid in known:
            item.add_marker(marker)
