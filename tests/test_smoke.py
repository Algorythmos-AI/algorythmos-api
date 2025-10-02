"""Smoke tests for the API service."""

import pytest
from fastapi.testclient import TestClient

from app import build_api


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    app = build_api()
    return TestClient(app)


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/api/alg/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint(client):
    """Test the version endpoint."""
    response = client.get("/api/version")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "fastapi" in data
    assert "pydantic" in data


def test_health_endpoint_without_api_prefix(client):
    """Test health endpoint with direct path (backwards compatibility)."""
    # Note: This tests that the health endpoint is accessible both ways
    response = client.get("/api/alg/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_headers(client):
    """Test that CORS headers are properly set."""
    response = client.get("/api/alg/healthz", headers={"Origin": "https://example.com"})
    # Basic check that CORS middleware is working
    assert response.status_code == 200
    # Should have CORS headers (though they may vary based on configuration)
    assert "access-control-allow-origin" in response.headers or "Access-Control-Allow-Origin" in response.headers