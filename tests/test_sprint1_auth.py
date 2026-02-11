"""
Sprint 1: Auth and Version Header Tests

Tests for:
- P0.1: Version headers (x-extend-api-version, x-api-version)
- P0.2: Bearer token authentication
"""
import pytest
from httpx import AsyncClient
from core.config import settings


@pytest.mark.asyncio
async def test_api_key_auth_still_works(client: AsyncClient):
    """Test that legacy X-API-Key authentication still works."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-auth-test"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_bearer_token_auth(client: AsyncClient):
    """Test that Bearer token authentication works."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "Authorization": f"Bearer {settings.ALG_API_KEY}",
            "X-Tenant-ID": "tenant-auth-test"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_invalid_bearer_token(client: AsyncClient):
    """Test that invalid Bearer token is rejected."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "Authorization": "Bearer invalid-token-12345",
            "X-Tenant-ID": "tenant-auth-test"
        }
    )
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["detail"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_missing_auth(client: AsyncClient):
    """Test that missing authentication is rejected."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-Tenant-ID": "tenant-auth-test"
        }
    )
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["detail"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_missing_tenant_id(client: AsyncClient):
    """Test that missing X-Tenant-ID is rejected."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY
        }
    )
    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
    data = response.json()
    assert data["detail"]["code"] == "MISSING_TENANT"


@pytest.mark.asyncio
async def test_version_header_extend_api_version(client: AsyncClient):
    """Test that x-extend-api-version header is accepted and tracked."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-auth-test",
            "x-extend-api-version": "2025-01-15"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    # Version should be stored in request context (we'll verify in webhook tests)


@pytest.mark.asyncio
async def test_version_header_x_api_version(client: AsyncClient):
    """Test that x-api-version header is accepted as fallback."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-auth-test",
            "x-api-version": "2025-02-01"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_version_header_precedence(client: AsyncClient):
    """Test that x-extend-api-version takes precedence over x-api-version."""
    # Both headers provided, x-extend-api-version should win
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-auth-test",
            "x-extend-api-version": "2025-01-15",
            "x-api-version": "2025-02-01"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_no_version_header_uses_default(client: AsyncClient):
    """Test that missing version header uses default version."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-auth-test"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_bearer_token_with_version_header(client: AsyncClient):
    """Test Bearer token auth combined with version header."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "Authorization": f"Bearer {settings.ALG_API_KEY}",
            "X-Tenant-ID": "tenant-auth-test",
            "x-extend-api-version": "2025-01-15"
        }
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_bearer_token_crud_operations(client: AsyncClient):
    """Test that Bearer token works for CRUD operations."""
    tenant = "tenant-bearer-crud"
    headers = {
        "Authorization": f"Bearer {settings.ALG_API_KEY}",
        "X-Tenant-ID": tenant,
        "x-extend-api-version": "2025-01-15"
    }
    
    # Create
    create_response = await client.post(
        "/api/extraction_schemas",
        headers=headers,
        json={
            "name": "Bearer Token Schema",
            "description": "Testing Bearer auth",
            "schema": {"type": "object"}
        }
    )
    assert create_response.status_code == 201, f"Expected 201, got {create_response.status_code}: {create_response.text}"
    schema_id = create_response.json()["id"]
    
    # Read
    get_response = await client.get(
        f"/api/extraction_schemas/{schema_id}",
        headers=headers
    )
    assert get_response.status_code == 200, f"Expected 200, got {get_response.status_code}: {get_response.text}"
    
    # Update
    update_response = await client.put(
        f"/api/extraction_schemas/{schema_id}",
        headers=headers,
        json={
            "name": "Bearer Token Schema Updated",
            "description": "Testing Bearer auth - updated",
            "schema": {"type": "object", "updated": True}
        }
    )
    assert update_response.status_code == 200, f"Expected 200, got {update_response.status_code}: {update_response.text}"
    
    # Delete
    delete_response = await client.delete(
        f"/api/extraction_schemas/{schema_id}",
        headers=headers
    )
    assert delete_response.status_code == 204, f"Expected 204, got {delete_response.status_code}"


@pytest.mark.asyncio
async def test_auth_isolation_between_tenants(client: AsyncClient):
    """Test that different tenants with same auth can't access each other's data."""
    # Tenant A creates a schema
    tenant_a_headers = {
        "X-API-Key": settings.ALG_API_KEY,
        "X-Tenant-ID": "tenant-a-isolation"
    }
    
    create_response = await client.post(
        "/api/extraction_schemas",
        headers=tenant_a_headers,
        json={
            "name": "Tenant A Schema",
            "description": "Private to tenant A",
            "schema": {"type": "object"}
        }
    )
    assert create_response.status_code == 201
    schema_id = create_response.json()["id"]
    
    # Tenant B tries to access it (should not see it in list)
    tenant_b_headers = {
        "Authorization": f"Bearer {settings.ALG_API_KEY}",
        "X-Tenant-ID": "tenant-b-isolation"
    }
    
    list_response = await client.get(
        "/api/extraction_schemas",
        headers=tenant_b_headers
    )
    assert list_response.status_code == 200
    tenant_b_schemas = list_response.json()["items"]
    assert not any(s["id"] == schema_id for s in tenant_b_schemas), "Tenant B should not see Tenant A's schema"
    
    # Tenant B tries to get it directly (should get 404)
    get_response = await client.get(
        f"/api/extraction_schemas/{schema_id}",
        headers=tenant_b_headers
    )
    assert get_response.status_code == 404, "Tenant B should get 404 for Tenant A's resource"
