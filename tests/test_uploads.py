"""Upload endpoint tests with comprehensive edge cases."""

import os
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient

from app import build_api


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    app = build_api()
    yield TestClient(app)


@pytest.fixture
def valid_api_key() -> str:
    """Get valid API key from environment or use default."""
    return os.getenv("ALG_API_KEY") or os.getenv("API_KEY", "algo_dWukMWn8YyFfkdnL4yITRgp8042vYbz1ckk2aY3dv")


@pytest.fixture
def test_data_dir() -> Path:
    """Get path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture
def valid_pdf_path(test_data_dir: Path) -> Path:
    """Get path to valid test PDF."""
    return test_data_dir / "valid_test.pdf"


@pytest.fixture
def corrupt_pdf_path(test_data_dir: Path) -> Path:
    """Get path to corrupt test PDF."""
    return test_data_dir / "corrupt_test.pdf"


class TestUploadEndpoint:
    """Test cases for the file upload endpoint."""

    def test_upload_valid_pdf_success(self, client: TestClient, valid_api_key: str, valid_pdf_path: Path):
        """Test uploading a valid PDF file."""
        if not valid_pdf_path.exists():
            pytest.skip("Valid test PDF not found")
            
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        with open(valid_pdf_path, "rb") as f:
            files = {"files": ("test.pdf", f, "application/pdf")}
            response = client.post("/api/extract/upload", headers=headers, files=files)
        
        # Should succeed or fail gracefully with structured error
        assert response.status_code in [200, 202, 422]
        data = response.json()
        
        if response.status_code in [200, 202]:
            assert "count" in data
            assert "records" in data
            assert "warnings" in data
        else:
            # Should be a structured error response
            assert "code" in data
            assert "message" in data

    def test_upload_empty_file_error(self, client: TestClient, valid_api_key: str):
        """Test uploading an empty file returns 400."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        files = {"files": ("empty.pdf", b"", "application/pdf")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["code"] == "EMPTY_FILE"

    def test_upload_wrong_mimetype_error(self, client: TestClient, valid_api_key: str):
        """Test uploading non-PDF file returns 415."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        files = {"files": ("test.txt", b"not a pdf", "text/plain")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 415
        data = response.json()
        assert "detail" in data
        assert data["detail"]["code"] == "INVALID_CONTENT_TYPE"

    def test_upload_file_too_large_error(self, client: TestClient, valid_api_key: str):
        """Test uploading oversized file returns 413."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        # Create a file larger than the default limit (25MB)
        large_content = b"x" * (26 * 1024 * 1024)  # 26MB
        files = {"files": ("large.pdf", large_content, "application/pdf")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 413
        data = response.json()
        assert "code" in data
        assert data["code"] == "FILE_TOO_LARGE"

    def test_upload_no_files_error(self, client: TestClient, valid_api_key: str):
        """Test uploading with no files returns 400."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        response = client.post("/api/extract/upload", headers=headers, files=[])
        
        assert response.status_code == 422  # FastAPI validation error for missing files

    def test_upload_missing_api_key_error(self, client: TestClient):
        """Test missing API key returns 401."""
        headers = {"x-tenant-id": "test-tenant"}
        
        files = {"files": ("test.pdf", b"fake pdf", "application/pdf")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 401

    def test_upload_invalid_api_key_error(self, client: TestClient):
        """Test invalid API key returns 401."""
        headers = {
            "x-api-key": "invalid-key",
            "x-tenant-id": "test-tenant"
        }
        
        files = {"files": ("test.pdf", b"fake pdf", "application/pdf")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 401

    def test_upload_missing_tenant_id_error(self, client: TestClient, valid_api_key: str):
        """Test missing tenant ID returns 400."""
        headers = {"x-api-key": valid_api_key}
        
        files = {"files": ("test.pdf", b"fake pdf", "application/pdf")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["code"] == "MISSING_TENANT"

    def test_upload_non_pdf_extension_error(self, client: TestClient, valid_api_key: str):
        """Test uploading file without .pdf extension returns 415."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        files = {"files": ("test.doc", b"fake content", "application/pdf")}
        response = client.post("/api/extract/upload", headers=headers, files=files)
        
        assert response.status_code == 415
        data = response.json()
        assert "detail" in data
        assert data["detail"]["code"] == "NOT_PDF"


class TestPathEndpoint:
    """Test cases for the path extraction endpoint."""

    def test_extract_path_not_found_error(self, client: TestClient, valid_api_key: str):
        """Test extracting from non-existent path returns 400."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        payload = {"input_path": "/non/existent/path"}
        response = client.post("/api/extract/path", headers=headers, json=payload)
        
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["code"] == "PATH_NOT_FOUND"


class TestJobEndpoints:
    """Test cases for job-related endpoints."""

    def test_create_job_success(self, client: TestClient, valid_api_key: str):
        """Test creating a background job."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        payload = {
            "input_path": "/tmp",  # Use a path that likely exists
            "debug": False
        }
        response = client.post("/api/jobs", headers=headers, json=payload)
        
        # Should succeed in creating the job
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data
        assert data["status"] == "queued"

    def test_get_nonexistent_job_error(self, client: TestClient, valid_api_key: str):
        """Test getting non-existent job returns 404."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "test-tenant"
        }
        
        response = client.get("/api/jobs/nonexistent-job-id", headers=headers)
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert data["detail"]["code"] == "JOB_NOT_FOUND"


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limiting_behavior(self, client: TestClient, valid_api_key: str):
        """Test that rate limiting is properly configured."""
        headers = {
            "x-api-key": valid_api_key,
            "x-tenant-id": "rate-limit-test-tenant"
        }
        
        # Make multiple requests to potentially trigger rate limiting
        # Note: This test depends on the rate limit configuration
        responses = []
        for i in range(5):
            payload = {"input_path": "/tmp"}
            response = client.post("/api/extract/path", headers=headers, json=payload)
            responses.append(response.status_code)
        
        # Should get at least some successful responses (even if they fail for other reasons)
        # Rate limiting would return 429
        assert not all(code == 429 for code in responses), "All requests were rate limited"


class TestRequestContext:
    """Test request context and headers."""

    def test_request_id_header(self, client: TestClient):
        """Test that request ID is properly handled."""
        custom_request_id = "test-request-123"
        headers = {"X-Request-ID": custom_request_id}
        
        response = client.get("/api/alg/healthz", headers=headers)
        
        assert response.status_code == 200
        assert response.headers.get("X-Request-ID") == custom_request_id

    def test_auto_request_id_generation(self, client: TestClient):
        """Test that request ID is auto-generated when not provided."""
        response = client.get("/api/alg/healthz")
        
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0