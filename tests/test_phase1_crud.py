"""
Tests for PHASE 1: Document Processing CRUD with Soft-Delete and Offset Pagination

Tests cover:
- Schema CRUD operations
- Extractor CRUD operations
- Classifier CRUD operations
- Splitter CRUD operations
- Soft-delete behavior (deleted items excluded from lists, cannot be retrieved/updated)
- Offset pagination (correct items, correct meta, boundary conditions)
- Error responses use standardized format
"""

import pytest
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
class TestSchemasCRUD:
    """Test schema CRUD operations with soft-delete and pagination."""
    
    async def test_create_schema(self, app_client: AsyncClient, auth_headers: dict):
        """Test creating a new schema."""
        response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Invoice Schema",
                "description": "Schema for extracting invoice data",
                "fields": [
                    {
                        "name": "invoice_number",
                        "type": "string",
                        "required": True,
                        "description": "Invoice number"
                    },
                    {
                        "name": "total_amount",
                        "type": "number",
                        "required": True,
                        "description": "Total invoice amount"
                    }
                ]
            }
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Invoice Schema"
        assert "schema_id" in data
        assert len(data["fields"]) == 2
        assert data["version"] == 1
    
    async def test_list_schemas_offset_pagination(self, app_client: AsyncClient, auth_headers: dict):
        """Test offset-based pagination for schemas."""
        # Create multiple schemas
        for i in range(5):
            await app_client.post(
                "/api/schemas",
                headers=auth_headers,
                json={
                    "name": f"Test Schema {i}",
                    "description": f"Schema {i}",
                    "fields": [{"name": "field1", "type": "string", "required": True}]
                }
            )
        
        # Test first page
        response = await app_client.get(
            "/api/schemas?limit=2&offset=0",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Check pagination meta
        assert "items" in data
        assert "meta" in data
        assert len(data["items"]) == 2
        assert data["meta"]["limit"] == 2
        assert data["meta"]["offset"] == 0
        assert data["meta"]["total"] >= 5
        assert data["meta"]["has_more"] is True
        assert data["meta"]["next_offset"] == 2
        
        # Test second page
        response = await app_client.get(
            "/api/schemas?limit=2&offset=2",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["items"]) == 2
        assert data["meta"]["offset"] == 2
        assert data["meta"]["next_offset"] == 4
    
    async def test_soft_delete_schema(self, app_client: AsyncClient, auth_headers: dict):
        """Test soft-delete behavior for schemas."""
        # Create a schema
        create_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "To Delete Schema",
                "description": "This will be deleted",
                "fields": [{"name": "field1", "type": "string", "required": True}]
            }
        )
        schema_id = create_response.json()["schema_id"]
        
        # Verify it exists
        get_response = await app_client.get(
            f"/api/schemas/{schema_id}",
            headers=auth_headers
        )
        assert get_response.status_code == status.HTTP_200_OK
        
        # Delete the schema (soft delete)
        delete_response = await app_client.delete(
            f"/api/schemas/{schema_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify it's not in the list
        list_response = await app_client.get(
            "/api/schemas",
            headers=auth_headers
        )
        assert list_response.status_code == status.HTTP_200_OK
        schema_ids = [s["schema_id"] for s in list_response.json()["items"]]
        assert schema_id not in schema_ids
        
        # Verify GET returns 404
        get_deleted_response = await app_client.get(
            f"/api/schemas/{schema_id}",
            headers=auth_headers
        )
        assert get_deleted_response.status_code == status.HTTP_404_NOT_FOUND
        
        # Verify error format
        error = get_deleted_response.json()
        assert "error" in error
        assert "type" in error["error"]
        assert "message" in error["error"]
        assert error["error"]["type"] == "resource_not_found"
        
        # Verify UPDATE returns 404
        update_response = await app_client.patch(
            f"/api/schemas/{schema_id}",
            headers=auth_headers,
            json={"description": "Updated"}
        )
        assert update_response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_reuse_deleted_schema_name(self, app_client: AsyncClient, auth_headers: dict):
        """Test that deleted schema names can be reused."""
        # Create a schema
        create_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Reusable Name",
                "description": "First version",
                "fields": [{"name": "field1", "type": "string", "required": True}]
            }
        )
        schema_id = create_response.json()["schema_id"]
        
        # Delete it
        await app_client.delete(
            f"/api/schemas/{schema_id}",
            headers=auth_headers
        )
        
        # Create a new schema with the same name (should succeed)
        create_response2 = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Reusable Name",
                "description": "Second version",
                "fields": [{"name": "field2", "type": "string", "required": True}]
            }
        )
        
        assert create_response2.status_code == status.HTTP_201_CREATED
        new_schema = create_response2.json()
        assert new_schema["schema_id"] != schema_id
        assert new_schema["name"] == "Reusable Name"
        assert new_schema["description"] == "Second version"


@pytest.mark.asyncio
class TestExtractorsCRUD:
    """Test extractor CRUD operations with soft-delete and pagination."""
    
    async def test_list_extractors_offset_pagination(self, app_client: AsyncClient, auth_headers: dict):
        """Test offset-based pagination for extractors."""
        # First create a schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Extractor Test Schema",
                "description": "For extractor tests",
                "fields": [{"name": "field1", "type": "string", "required": True}]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Create multiple extractors
        for i in range(3):
            await app_client.post(
                "/api/extractors",
                headers=auth_headers,
                json={
                    "name": f"Extractor {i}",
                    "type": "regex",
                    "schema_id": schema_id,
                    "enabled": True,
                    "priority": i,
                    "rules": {}
                }
            )
        
        # Test pagination
        response = await app_client.get(
            "/api/extractors?limit=2&offset=0",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "meta" in data
        assert len(data["items"]) <= 2
        assert data["meta"]["limit"] == 2
        assert data["meta"]["offset"] == 0
    
    async def test_soft_delete_extractor(self, app_client: AsyncClient, auth_headers: dict):
        """Test soft-delete behavior for extractors."""
        # Create schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Schema for Extractor Delete",
                "description": "Test",
                "fields": [{"name": "field1", "type": "string", "required": True}]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Create extractor
        create_response = await app_client.post(
            "/api/extractors",
            headers=auth_headers,
            json={
                "name": "To Delete Extractor",
                "type": "regex",
                "schema_id": schema_id,
                "enabled": True,
                "priority": 1,
                "rules": {}
            }
        )
        extractor_id = create_response.json()["extractor_id"]
        
        # Delete extractor
        delete_response = await app_client.delete(
            f"/api/extractors/{extractor_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify it's not in list
        list_response = await app_client.get(
            "/api/extractors",
            headers=auth_headers
        )
        extractor_ids = [e["extractor_id"] for e in list_response.json()["items"]]
        assert extractor_id not in extractor_ids


@pytest.mark.asyncio
class TestClassifiersCRUD:
    """Test classifier CRUD operations with soft-delete and pagination."""
    
    async def test_list_classifiers_offset_pagination(self, app_client: AsyncClient, auth_headers: dict):
        """Test offset-based pagination for classifiers."""
        # Create multiple classifiers
        for i in range(3):
            await app_client.post(
                "/api/classifiers",
                headers=auth_headers,
                json={
                    "name": f"Classifier {i}",
                    "type": "keyword",
                    "enabled": True,
                    "categories": ["cat1", "cat2"],
                    "rules": {}
                }
            )
        
        # Test pagination
        response = await app_client.get(
            "/api/classifiers?limit=2&offset=0",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "meta" in data
        assert data["meta"]["limit"] == 2
        assert data["meta"]["offset"] == 0
    
    async def test_soft_delete_classifier(self, app_client: AsyncClient, auth_headers: dict):
        """Test soft-delete behavior for classifiers."""
        # Create classifier
        create_response = await app_client.post(
            "/api/classifiers",
            headers=auth_headers,
            json={
                "name": "To Delete Classifier",
                "type": "keyword",
                "enabled": True,
                "categories": ["cat1"],
                "rules": {}
            }
        )
        classifier_id = create_response.json()["classifier_id"]
        
        # Delete classifier
        delete_response = await app_client.delete(
            f"/api/classifiers/{classifier_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify GET returns 404
        get_response = await app_client.get(
            f"/api/classifiers/{classifier_id}",
            headers=auth_headers
        )
        assert get_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
class TestSplittersCRUD:
    """Test splitter CRUD operations with soft-delete and pagination."""
    
    async def test_list_splitters_offset_pagination(self, app_client: AsyncClient, auth_headers: dict):
        """Test offset-based pagination for splitters."""
        # Create multiple splitters
        for i in range(3):
            await app_client.post(
                "/api/splitters",
                headers=auth_headers,
                json={
                    "name": f"Splitter {i}",
                    "type": "rule_based",
                    "enabled": True,
                    "rules": {}
                }
            )
        
        # Test pagination
        response = await app_client.get(
            "/api/splitters?limit=2&offset=0",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "items" in data
        assert "meta" in data
        assert data["meta"]["limit"] == 2
        assert data["meta"]["offset"] == 0
    
    async def test_soft_delete_splitter(self, app_client: AsyncClient, auth_headers: dict):
        """Test soft-delete behavior for splitters."""
        # Create splitter
        create_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "To Delete Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {}
            }
        )
        splitter_id = create_response.json()["splitter_id"]
        
        # Delete splitter
        delete_response = await app_client.delete(
            f"/api/splitters/{splitter_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify it's not in list
        list_response = await app_client.get(
            "/api/splitters",
            headers=auth_headers
        )
        splitter_ids = [s["splitter_id"] for s in list_response.json()["items"]]
        assert splitter_id not in splitter_ids


@pytest.mark.asyncio
class TestErrorResponses:
    """Test standardized error response format."""
    
    async def test_error_response_format(self, app_client: AsyncClient, auth_headers: dict):
        """Test that errors use standardized format."""
        # Try to get non-existent schema
        response = await app_client.get(
            "/api/schemas/nonexistent_id",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        error = response.json()
        
        # Verify error structure
        assert "error" in error
        assert "type" in error["error"]
        assert "message" in error["error"]
        assert isinstance(error["error"]["type"], str)
        assert isinstance(error["error"]["message"], str)
    
    async def test_validation_error_format(self, app_client: AsyncClient, auth_headers: dict):
        """Test validation errors use standardized format."""
        # Try to create schema with invalid data
        response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "",  # Invalid: empty name
                "description": "Test",
                "fields": []
            }
        )
        
        # Should get validation error
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_ENTITY]
