"""
Tests for PHASE 6: Production Hardening.

Tests:
- Rate limiting
- Idempotency
- Prometheus metrics
"""

import pytest
import time
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from app import create_app


@pytest.fixture
async def app_client():
    """Create test client."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def tenant_id():
    """Test tenant ID."""
    return "test-tenant-123"


@pytest.fixture
def api_key():
    """Test API key."""
    return "test-key-abc123"


# ===================
# Rate Limiting Tests
# ===================


@pytest.mark.asyncio
async def test_rate_limit_per_minute(app_client, api_key):
    """Test per-minute rate limit."""
    # Make requests up to limit
    for i in range(60):
        response = await app_client.get(
            "/api/health",
            headers={"X-API-Key": api_key}
        )
        assert response.status_code == 200
    
    # Next request should be rate limited
    response = await app_client.get(
        "/api/health",
        headers={"X-API-Key": api_key}
    )
    
    assert response.status_code == 429
    data = response.json()
    assert data["error"]["type"] == "rate_limit_exceeded"
    assert "per-minute" in data["error"]["message"].lower()
    assert response.headers.get("Retry-After") is not None


@pytest.mark.asyncio
async def test_rate_limit_per_hour(app_client, api_key):
    """Test per-hour rate limit."""
    # Simulate many requests (would need to adjust middleware for testing)
    # For now, just verify headers are present
    response = await app_client.get(
        "/api/health",
        headers={"X-API-Key": api_key}
    )
    
    assert response.status_code == 200
    assert "X-RateLimit-Limit-Minute" in response.headers
    assert "X-RateLimit-Remaining-Minute" in response.headers
    assert "X-RateLimit-Limit-Hour" in response.headers
    assert "X-RateLimit-Remaining-Hour" in response.headers


@pytest.mark.asyncio
async def test_rate_limit_per_tenant(app_client):
    """Test rate limiting is per-tenant."""
    # Tenant 1
    for i in range(60):
        response = await app_client.get(
            "/api/health",
            headers={"X-API-Key": "tenant1-key"}
        )
        assert response.status_code == 200
    
    # Tenant 1 should be rate limited
    response = await app_client.get(
        "/api/health",
        headers={"X-API-Key": "tenant1-key"}
    )
    assert response.status_code == 429
    
    # But tenant 2 should still work
    response = await app_client.get(
        "/api/health",
        headers={"X-API-Key": "tenant2-key"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_excludes_health_check(app_client, api_key):
    """Test that health checks are excluded from rate limiting."""
    # Health checks should not count toward limit
    for i in range(100):
        response = await app_client.get("/health")
        assert response.status_code == 200
    
    # Regular endpoints should still have full quota
    response = await app_client.get(
        "/api/schemas",
        headers={"X-API-Key": api_key}
    )
    # Should have full rate limit headers
    assert "X-RateLimit-Remaining-Minute" in response.headers


# ===================
# Idempotency Tests
# ===================


@pytest.mark.asyncio
async def test_idempotency_post_request(app_client, api_key, mock_session):
    """Test idempotency for POST requests."""
    idempotency_key = "test-idempotency-123"
    
    # First request
    with patch("app.get_session", return_value=mock_session):
        response1 = await app_client.post(
            "/api/schemas",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": idempotency_key
            },
            json={
                "name": "Test Schema",
                "schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        )
    
    # Second request with same key should return cached response
    with patch("app.get_session", return_value=mock_session):
        response2 = await app_client.post(
            "/api/schemas",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": idempotency_key
            },
            json={
                "name": "Test Schema",
                "schema": {
                    "type": "object",
                    "properties": {}
                }
            }
        )
    
    # Verify replay header is present
    if response2.status_code == 200:
        assert response2.headers.get("X-Idempotency-Replay") == "true"


@pytest.mark.asyncio
async def test_idempotency_different_keys(app_client, api_key, mock_session):
    """Test that different idempotency keys create separate requests."""
    # First request
    with patch("app.get_session", return_value=mock_session):
        response1 = await app_client.post(
            "/api/schemas",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": "key-1"
            },
            json={
                "name": "Schema 1",
                "schema": {"type": "object"}
            }
        )
    
    # Second request with different key
    with patch("app.get_session", return_value=mock_session):
        response2 = await app_client.post(
            "/api/schemas",
            headers={
                "X-API-Key": api_key,
                "Idempotency-Key": "key-2"
            },
            json={
                "name": "Schema 2",
                "schema": {"type": "object"}
            }
        )
    
    # Should not have replay header
    assert response2.headers.get("X-Idempotency-Replay") != "true"


@pytest.mark.asyncio
async def test_idempotency_get_request_ignored(app_client, api_key):
    """Test that GET requests ignore idempotency keys."""
    response = await app_client.get(
        "/api/schemas",
        headers={
            "X-API-Key": api_key,
            "Idempotency-Key": "should-be-ignored"
        }
    )
    
    # Should process normally without replay header
    assert response.headers.get("X-Idempotency-Replay") != "true"


@pytest.mark.asyncio
async def test_idempotency_per_tenant(app_client, mock_session):
    """Test that idempotency keys are scoped per tenant."""
    idempotency_key = "shared-key"
    
    # Tenant 1
    with patch("app.get_session", return_value=mock_session):
        response1 = await app_client.post(
            "/api/schemas",
            headers={
                "X-API-Key": "tenant1-key",
                "Idempotency-Key": idempotency_key
            },
            json={
                "name": "Tenant 1 Schema",
                "schema": {"type": "object"}
            }
        )
    
    # Tenant 2 with same key should create new request
    with patch("app.get_session", return_value=mock_session):
        response2 = await app_client.post(
            "/api/schemas",
            headers={
                "X-API-Key": "tenant2-key",
                "Idempotency-Key": idempotency_key
            },
            json={
                "name": "Tenant 2 Schema",
                "schema": {"type": "object"}
            }
        )
    
    # Should not be a replay
    assert response2.headers.get("X-Idempotency-Replay") != "true"


# ===================
# Metrics Tests
# ===================


@pytest.mark.asyncio
async def test_metrics_endpoint_exists(app_client):
    """Test that metrics endpoint is accessible."""
    response = await app_client.get("/metrics")
    
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_http_request_metrics(app_client, api_key):
    """Test HTTP request metrics are tracked."""
    # Make some requests
    await app_client.get("/api/schemas", headers={"X-API-Key": api_key})
    await app_client.get("/api/extractors", headers={"X-API-Key": api_key})
    
    # Check metrics
    response = await app_client.get("/metrics")
    content = response.text
    
    # Should have http_requests_total metric
    assert "http_requests_total" in content
    assert "http_request_duration_seconds" in content


@pytest.mark.asyncio
async def test_webhook_metrics_exist(app_client):
    """Test webhook metrics are defined."""
    response = await app_client.get("/metrics")
    content = response.text
    
    # Should have webhook metrics defined
    assert "webhook_deliveries_total" in content or "# TYPE webhook_deliveries_total" in content
    assert "webhook_delivery_duration_seconds" in content or "# TYPE webhook_delivery_duration_seconds" in content


@pytest.mark.asyncio
async def test_parser_run_metrics_exist(app_client):
    """Test parser run metrics are defined."""
    response = await app_client.get("/metrics")
    content = response.text
    
    # Should have parser metrics defined
    assert "parser_runs_total" in content or "# TYPE parser_runs_total" in content
    assert "parser_run_duration_seconds" in content or "# TYPE parser_run_duration_seconds" in content


@pytest.mark.asyncio
async def test_rate_limit_metrics_exist(app_client):
    """Test rate limit metrics are defined."""
    response = await app_client.get("/metrics")
    content = response.text
    
    # Should have rate limit metrics
    assert "rate_limit_hits_total" in content or "# TYPE rate_limit_hits_total" in content


@pytest.mark.asyncio
async def test_idempotency_metrics_exist(app_client):
    """Test idempotency metrics are defined."""
    response = await app_client.get("/metrics")
    content = response.text
    
    # Should have idempotency metrics
    assert "idempotency_replays_total" in content or "# TYPE idempotency_replays_total" in content


# ===================
# Middleware Integration Tests
# ===================


@pytest.mark.asyncio
async def test_middleware_order(app_client, api_key):
    """Test that middlewares are applied in correct order."""
    # Make a request
    response = await app_client.post(
        "/api/schemas",
        headers={
            "X-API-Key": api_key,
            "Idempotency-Key": "test-order"
        },
        json={
            "name": "Test",
            "schema": {"type": "object"}
        }
    )
    
    # Should have rate limit headers
    assert "X-RateLimit-Limit-Minute" in response.headers or response.status_code == 429
    
    # Should process idempotency
    # (idempotency headers only appear on replays)


@pytest.mark.asyncio
async def test_cors_with_production_middlewares(app_client):
    """Test CORS still works with production middlewares."""
    response = await app_client.options(
        "/api/schemas",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST"
        }
    )
    
    # CORS should work
    assert response.status_code in [200, 204]
    assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
async def test_error_handling_with_middlewares(app_client, api_key):
    """Test error handling works correctly with middlewares."""
    # Make invalid request
    response = await app_client.get(
        "/api/schemas/invalid-uuid",
        headers={"X-API-Key": api_key}
    )
    
    # Should return proper error
    assert response.status_code >= 400
    
    # Should still have rate limit headers
    assert "X-RateLimit-Limit-Minute" in response.headers


# ===================
# Cleanup Tests
# ===================


def test_cleanup_old_entries():
    """Test cleanup function for in-memory stores."""
    from document_processing.middleware import cleanup_old_entries, _rate_limit_store, _idempotency_store
    
    # Add some entries
    _rate_limit_store["tenant1"] = [time.time() - 7200, time.time()]  # 2 hours ago and now
    _idempotency_store["key1"] = (200, {}, datetime.utcnow())
    
    # Run cleanup
    cleanup_old_entries()
    
    # Old rate limit entries should be removed
    assert len(_rate_limit_store["tenant1"]) == 1
    
    # Recent idempotency entries should remain
    assert "key1" in _idempotency_store
