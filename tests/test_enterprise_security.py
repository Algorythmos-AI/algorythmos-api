"""
Enterprise-Level Security and Resilience Tests

Comprehensive tests covering:
- Auth hardening (injection, malformed headers, edge cases)
- Health endpoint verification
- Input validation and boundary testing
- Tenant isolation enforcement
- Idempotency behaviour
- CORS and security headers
"""

import pytest
from httpx import AsyncClient

from config import settings


# ============================================================================
# Auth Hardening
# ============================================================================


@pytest.mark.asyncio
async def test_sql_injection_in_api_key_header(client: AsyncClient):
    """Ensure SQL-injection payloads in X-API-Key are rejected."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": "' OR '1'='1",
            "X-Tenant-ID": "tenant-sec",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sql_injection_in_tenant_header(client: AsyncClient):
    """Ensure SQL-injection payloads in X-Tenant-ID don't bypass isolation."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "'; DROP TABLE extraction_schemas;--",
        },
    )
    # Should succeed (tenant IDs are opaque strings) but return empty results
    assert response.status_code in (200, 400)


@pytest.mark.asyncio
async def test_empty_bearer_token_rejected(client: AsyncClient):
    """Empty Bearer token must be rejected."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "Authorization": "Bearer ",
            "X-Tenant-ID": "tenant-sec",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bearer_without_space_rejected(client: AsyncClient):
    """Malformed Authorization header without space after Bearer."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "Authorization": "Bearersome-token",
            "X-Tenant-ID": "tenant-sec",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_basic_auth_scheme_rejected(client: AsyncClient):
    """Non-Bearer auth schemes should be rejected."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "Authorization": "Basic dXNlcjpwYXNz",
            "X-Tenant-ID": "tenant-sec",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oversized_api_key_rejected(client: AsyncClient):
    """Extremely long API keys should be handled gracefully."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": "A" * 10_000,
            "X-Tenant-ID": "tenant-sec",
        },
    )
    assert response.status_code == 401


# ============================================================================
# Health Endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_healthz_returns_200(app_client: AsyncClient):
    """Health endpoint must return HTTP 200."""
    response = await app_client.get("/alg/healthz")
    if response.status_code == 404:
        response = await app_client.get("/api/alg/healthz")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_healthz_returns_json(app_client: AsyncClient):
    """Health endpoint must return valid JSON."""
    response = await app_client.get("/alg/healthz")
    if response.status_code == 404:
        response = await app_client.get("/api/alg/healthz")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)


# ============================================================================
# Input Validation
# ============================================================================


@pytest.mark.asyncio
async def test_empty_body_on_post_endpoint(client: AsyncClient):
    """POST with empty body should return 422 validation error."""
    response = await client.post(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-validation",
        },
        content=b"",
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_json_on_post_endpoint(client: AsyncClient):
    """POST with malformed JSON should return 422."""
    response = await client.post(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-validation",
            "Content-Type": "application/json",
        },
        content=b"{invalid json}",
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unicode_tenant_id_accepted(client: AsyncClient):
    """Unicode characters in tenant ID should be handled gracefully."""
    response = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-日本語-テスト",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_nonexistent_resource_returns_404(client: AsyncClient):
    """GET on non-existent resource should return 404, not 500."""
    response = await client.get(
        "/api/extraction_schemas/nonexistent-id-999",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-validation",
        },
    )
    assert response.status_code == 404


# ============================================================================
# Tenant Isolation (expanded)
# ============================================================================


@pytest.mark.asyncio
async def test_tenant_cannot_list_other_tenant_schemas(client: AsyncClient):
    """Verify strict tenant isolation on list endpoints."""
    # Tenant A creates a schema
    create_resp = await client.post(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-iso-alpha",
        },
        json={
            "name": "Alpha Schema",
            "description": "Private to alpha",
            "schema": {"type": "object"},
        },
    )
    assert create_resp.status_code == 201

    # Tenant B lists — should not contain Tenant A's schema
    list_resp = await client.get(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-iso-beta",
        },
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    alpha_ids = [s["id"] for s in items if s.get("name") == "Alpha Schema"]
    assert len(alpha_ids) == 0, "Tenant beta must not see tenant alpha's schemas"


@pytest.mark.asyncio
async def test_tenant_cannot_delete_other_tenant_resource(client: AsyncClient):
    """Verify cross-tenant delete is blocked."""
    # Tenant A creates
    create_resp = await client.post(
        "/api/extraction_schemas",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-iso-create",
        },
        json={
            "name": "Delete Test Schema",
            "description": "For cross-tenant delete test",
            "schema": {"type": "object"},
        },
    )
    assert create_resp.status_code == 201
    schema_id = create_resp.json()["id"]

    # Tenant B tries to delete — should get 404 (invisible to them)
    del_resp = await client.delete(
        f"/api/extraction_schemas/{schema_id}",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-iso-attacker",
        },
    )
    assert del_resp.status_code == 404


# ============================================================================
# CRUD Lifecycle
# ============================================================================


@pytest.mark.asyncio
async def test_full_crud_lifecycle(client: AsyncClient):
    """Validate complete Create → Read → Update → Delete lifecycle."""
    tenant = "tenant-crud-lifecycle"
    headers = {
        "X-API-Key": settings.ALG_API_KEY,
        "X-Tenant-ID": tenant,
    }

    # Create
    create = await client.post(
        "/api/extraction_schemas",
        headers=headers,
        json={
            "name": "Lifecycle Schema",
            "description": "E2E lifecycle",
            "schema": {"type": "object"},
        },
    )
    assert create.status_code == 201
    schema_id = create.json()["id"]

    # Read
    get = await client.get(f"/api/extraction_schemas/{schema_id}", headers=headers)
    assert get.status_code == 200
    assert get.json()["name"] == "Lifecycle Schema"

    # Update
    put = await client.put(
        f"/api/extraction_schemas/{schema_id}",
        headers=headers,
        json={
            "name": "Updated Schema",
            "description": "Updated",
            "schema": {"type": "object", "updated": True},
        },
    )
    assert put.status_code == 200
    assert put.json()["name"] == "Updated Schema"

    # Delete
    delete = await client.delete(f"/api/extraction_schemas/{schema_id}", headers=headers)
    assert delete.status_code == 204

    # Verify gone
    verify = await client.get(f"/api/extraction_schemas/{schema_id}", headers=headers)
    assert verify.status_code == 404


# ============================================================================
# Config Validation
# ============================================================================


def test_production_settings_require_api_key():
    """Production env must enforce ALG_API_KEY is present."""
    from config import Settings

    with pytest.raises(Exception):
        Settings(
            ALG_API_KEY="",
            ENV="production",
            GOOGLE_CLIENT_ID="prod.apps.googleusercontent.com",
            REDIS_URL="redis://localhost:6379/0",
        )


def test_production_settings_require_google_client_id():
    """Production env must enforce GOOGLE_CLIENT_ID."""
    from config import Settings

    with pytest.raises(ValueError, match="GOOGLE_CLIENT_ID"):
        Settings(
            ALG_API_KEY="prod-key",
            ENV="production",
            GOOGLE_CLIENT_ID=None,
            REDIS_URL="redis://localhost:6379/0",
        )


def test_production_settings_reject_memory_backend():
    """Production must not allow STATE_BACKEND=memory."""
    from config import Settings

    with pytest.raises(ValueError, match="memory"):
        Settings(
            ALG_API_KEY="prod-key",
            ENV="production",
            GOOGLE_CLIENT_ID="prod.apps.googleusercontent.com",
            REDIS_URL="redis://localhost:6379/0",
            STATE_BACKEND="memory",
        )


# ============================================================================
# Schema Module Completeness
# ============================================================================


def test_all_schema_modules_importable():
    """All Pydantic schema modules must be importable without error."""
    modules = [
        "document_processing.schemas",
        "document_processing.schemas_parse",
        "document_processing.schemas_processor_versions",
        "document_processing.schemas_processor_runs",
        "document_processing.schemas_workflow_runs",
        "document_processing.schemas_eval_items",
    ]
    for mod_name in modules:
        mod = __import__(mod_name, fromlist=["__name__"])
        assert mod is not None, f"{mod_name} failed to import"


def test_all_service_modules_importable():
    """Core service modules must be importable."""
    modules = [
        "document_processing.services.schema_service",
        "document_processing.services.extractor_service",
        "document_processing.services.processor_service",
    ]
    for mod_name in modules:
        mod = __import__(mod_name, fromlist=["__name__"])
        assert mod is not None, f"{mod_name} failed to import"
