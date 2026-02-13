from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("API_KEY", "local_dummy")

from service import app

client = TestClient(app)
HEADERS = {"X-Tenant-Id": "tenant-test", "X-Api-Key": os.environ["API_KEY"]}
SOURCE_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "files"
EXPECTED_FILES = [
    "facture_9099017876_2025-05-06-2.pdf",
    "facture_9099017876_2025-06-06.pdf",
    "facture_9099017876_2025-07-07.pdf",
    "facture_9099017876_2025-08-06-2.pdf",
    "facture_9099017876_2025-09-08.pdf",
]


@pytest.fixture(scope="module")
def fixture_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create deterministic fixture directory with only the expected 5 PDFs."""
    dest = tmp_path_factory.mktemp("service-smoke-files")
    for filename in EXPECTED_FILES:
        shutil.copy2(SOURCE_FIXTURE_DIR / filename, dest / filename)
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
        ("facture_9099017876_2025-05-06-2.pdf", "2025-05-06", "2025-05-02", "2025-06-01", 6.221),
        ("facture_9099017876_2025-06-06.pdf", "2025-06-06", "2025-05-02", "2025-06-01", 41.4),
        ("facture_9099017876_2025-07-07.pdf", "2025-07-07", "2025-07-02", "2025-08-01", 81.6),
        ("facture_9099017876_2025-08-06-2.pdf", "2025-08-06", "2025-08-02", "2025-09-01", 88.2),
        ("facture_9099017876_2025-09-08.pdf", "2025-09-08", "2025-09-02", "2025-10-01", 99.0),
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
        json={"input_path": str(SOURCE_FIXTURE_DIR)},
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
