import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import app as fastapi_app

API_BASE = os.getenv("API_BASE", "").strip()
URL = f"{API_BASE.rstrip('/')}/vendor/healthz" if API_BASE else "/api/vendor/healthz"

# Fast = under 1s even if vendor is down (should return 204 when up, 502 when down)
FAST_THRESHOLD_SEC = float(os.getenv("VENDOR_HEALTH_FAST_SEC", "1.0"))
# Stable = multiple hits stay consistently fast; we'll sample 5 times
SAMPLES = int(os.getenv("VENDOR_HEALTH_SAMPLES", "5"))
TIMEOUT_SEC = float(os.getenv("VENDOR_HEALTH_TIMEOUT_SEC", "2.0"))


def _probe_vendor_health() -> tuple[int, float]:
    start = time.monotonic()
    if API_BASE:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.get(URL)
    else:
        with TestClient(fastapi_app) as client:
            response = client.get(URL)
    elapsed = time.monotonic() - start
    return response.status_code, elapsed

@pytest.mark.timeout(10)
def test_vendor_healthz_fast():
    status_code, elapsed = _probe_vendor_health()

    assert status_code in (204, 502), f"Unexpected status: {status_code}"
    assert elapsed < FAST_THRESHOLD_SEC, f"Too slow: {elapsed:.3f}s (threshold {FAST_THRESHOLD_SEC}s)"

@pytest.mark.timeout(30)
def test_vendor_healthz_stable_under_threshold():
    durations = []
    statuses = []
    for _ in range(SAMPLES):
        status_code, elapsed = _probe_vendor_health()
        durations.append(elapsed)
        statuses.append(status_code)

    # 95th percentile (or max if few samples) is under threshold
    p95 = sorted(durations)[max(0, int(0.95 * (len(durations)-1)))]
    assert all(s in (204, 502) for s in statuses), f"Unexpected status codes: {statuses}"
    assert p95 < FAST_THRESHOLD_SEC, f"p95 {p95:.3f}s over threshold {FAST_THRESHOLD_SEC}s"
