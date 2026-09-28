from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fixtures.synthetic_invoices import SYNTHETIC_INVOICES, write_synthetic_invoices

os.environ.setdefault("API_KEY", "local_dummy")

from service import app

client = TestClient(app)
API_KEY = os.environ.get("ALG_API_KEY") or os.environ["API_KEY"]
HEADERS = {"X-Tenant-Id": "tenant-test", "X-Api-Key": API_KEY}


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the five synthetic invoices into a fresh directory."""
    dest = tmp_path_factory.mktemp("service-smoke-files")
    write_synthetic_invoices(dest)
    return dest


def test_extract_path_smoke(fixture_dir: Path) -> None:
    response = client.post(
        "/extract/path",
        json={"input_path": str(fixture_dir)},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["count"] == 5

    expected = [
        (
            inv.filename,
            inv.invoice_date.isoformat(),
            inv.period_start.isoformat(),
            inv.period_end.isoformat(),
            inv.internet_gb,
        )
        for inv in SYNTHETIC_INVOICES
    ]

    records = payload["records"]
    assert [record["file"] for record in records] == [item[0] for item in expected]

    for record, exp in zip(records, expected):
        _, invoice_date, period_start, period_end, internet_gb = exp
        assert record["invoice_date"] == invoice_date
        assert record["period_start"] == period_start
        assert record["period_end"] == period_end
        assert record["internet_gb"] == internet_gb
        assert record["confidence"] > 0.5

    assert payload["warnings"] == []


def test_extract_path_requires_tenant_header() -> None:
    response = client.post(
        "/extract/path",
        json={"input_path": "/nonexistent"},
    )
    assert response.status_code in (400, 401)


def test_job_lifecycle(fixture_dir: Path) -> None:
    response = client.post(
        "/jobs",
        json={"input_path": str(fixture_dir)},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text
    job_data = response.json()
    job_id = job_data["job_id"]

    # Poll for completion
    for _ in range(10):
        status_response = client.get(f"/jobs/{job_id}", headers=HEADERS)
        assert status_response.status_code == 200
        status_payload = status_response.json()
        if status_payload["status"] == "succeeded":
            assert status_payload["result"]["count"] == 5
            break
        time.sleep(0.1)
    else:  # pragma: no cover - should not happen, ensures test fails loudly
        raise AssertionError("job did not complete")
