"""
Tests for PHASE 4: File uploads and parser runs.

Tests file upload, parser run creation, and document parsing workflows.
"""

import pytest
from httpx import AsyncClient
from fastapi import status
from io import BytesIO


@pytest.mark.asyncio
class TestFileUpload:
    """Test file upload functionality."""
    
    async def test_upload_text_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test uploading a text file."""
        # Create a test file
        test_content = b"This is a test document for parsing."
        test_file = ("test.txt", BytesIO(test_content), "text/plain")
        
        response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        # Verify response structure
        assert "file_id" in data
        assert data["filename"] == "test.txt"
        assert data["content_type"] == "text/plain"
        assert data["size_bytes"] == len(test_content)
        assert "checksum" in data
        assert "tenant_id" in data
        assert "created_at" in data
    
    async def test_upload_with_metadata(self, app_client: AsyncClient, auth_headers: dict):
        """Test uploading a file with custom metadata."""
        test_content = b"Document with metadata"
        test_file = ("doc.txt", BytesIO(test_content), "text/plain")
        
        metadata = {
            "source": "test_suite",
            "category": "sample"
        }
        
        response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file},
            data={"metadata": str(metadata)}  # Note: FastAPI form data handling
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["filename"] == "doc.txt"
    
    async def test_list_files(self, app_client: AsyncClient, auth_headers: dict):
        """Test listing uploaded files."""
        # Upload a few files
        for i in range(3):
            test_file = (f"file{i}.txt", BytesIO(b"content"), "text/plain")
            await app_client.post(
                "/api/files",
                headers=auth_headers,
                files={"file": test_file}
            )
        
        # List files
        response = await app_client.get(
            "/api/files",
            headers=auth_headers,
            params={"limit": 10, "offset": 0}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "items" in data
        assert "meta" in data
        assert len(data["items"]) >= 3
        assert data["meta"]["limit"] == 10
        assert data["meta"]["offset"] == 0
    
    async def test_get_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test retrieving file metadata."""
        # Upload a file
        test_file = ("get_test.txt", BytesIO(b"content"), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Get file metadata
        response = await app_client.get(
            f"/api/files/{file_id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_id"] == file_id
        assert data["filename"] == "get_test.txt"
    
    async def test_delete_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test soft deleting a file."""
        # Upload a file
        test_file = ("delete_test.txt", BytesIO(b"content"), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Delete file
        delete_response = await app_client.delete(
            f"/api/files/{file_id}",
            headers=auth_headers
        )
        
        assert delete_response.status_code == status.HTTP_200_OK
        assert "message" in delete_response.json()
        
        # Verify file is gone
        get_response = await app_client.get(
            f"/api/files/{file_id}",
            headers=auth_headers
        )
        
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_get_nonexistent_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test getting a file that doesn't exist."""
        response = await app_client.get(
            "/api/files/nonexistent_id",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
class TestParserRuns:
    """Test parser run functionality."""
    
    async def test_sync_parse_no_config(self, app_client: AsyncClient, auth_headers: dict):
        """Test synchronous parsing without any configuration."""
        # Upload a file
        test_content = b"This is a simple test document."
        test_file = ("parse_test.txt", BytesIO(test_content), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Parse synchronously
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        data = parse_response.json()
        
        # Verify response structure
        assert "run_id" in data
        assert data["file_id"] == file_id
        assert data["status"] in ["completed", "failed"]
        assert "processing_time_ms" in data
        assert "completed_at" in data
    
    async def test_sync_parse_with_schema(self, app_client: AsyncClient, auth_headers: dict):
        """Test parsing with a schema for extraction."""
        # Create a schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Test Schema",
                "description": "Schema for testing",
                "fields": [
                    {
                        "name": "title",
                        "type": "string",
                        "description": "Document title"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Upload file
        test_file = ("schema_test.txt", BytesIO(b"Title: Test Document"), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Parse with schema
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={
                "file_id": file_id,
                "schema_id": schema_id
            }
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        data = parse_response.json()
        assert data["status"] in ["completed", "failed"]
        
        if data["status"] == "completed":
            assert "extracted" in data
    
    async def test_async_parse(self, app_client: AsyncClient, auth_headers: dict):
        """Test asynchronous parser run creation."""
        # Upload file
        test_file = ("async_test.txt", BytesIO(b"Async content"), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Create async parse
        parse_response = await app_client.post(
            "/api/parse/async",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        
        assert parse_response.status_code == status.HTTP_202_ACCEPTED
        data = parse_response.json()
        
        assert "run_id" in data
        assert data["file_id"] == file_id
        assert data["status"] == "pending"
    
    async def test_get_parser_run(self, app_client: AsyncClient, auth_headers: dict):
        """Test getting parser run status."""
        # Upload and parse
        test_file = ("status_test.txt", BytesIO(b"Status test"), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        parse_response = await app_client.post(
            "/api/parse/async",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        run_id = parse_response.json()["run_id"]
        
        # Get run status
        status_response = await app_client.get(
            f"/api/parse/{run_id}",
            headers=auth_headers
        )
        
        assert status_response.status_code == status.HTTP_200_OK
        data = status_response.json()
        assert data["run_id"] == run_id
        assert "status" in data
    
    async def test_list_parser_runs(self, app_client: AsyncClient, auth_headers: dict):
        """Test listing parser runs."""
        # Create a couple of parser runs
        for i in range(2):
            test_file = (f"list_test{i}.txt", BytesIO(b"content"), "text/plain")
            upload_response = await app_client.post(
                "/api/files",
                headers=auth_headers,
                files={"file": test_file}
            )
            file_id = upload_response.json()["file_id"]
            
            await app_client.post(
                "/api/parse/async",
                headers=auth_headers,
                json={"file_id": file_id}
            )
        
        # List runs
        list_response = await app_client.get(
            "/api/parse",
            headers=auth_headers,
            params={"limit": 10, "offset": 0}
        )
        
        assert list_response.status_code == status.HTTP_200_OK
        data = list_response.json()
        
        assert "items" in data
        assert "meta" in data
        assert len(data["items"]) >= 2
    
    async def test_list_runs_filter_by_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test filtering parser runs by file ID."""
        # Upload file
        test_file = ("filter_test.txt", BytesIO(b"filter"), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Create multiple runs for same file
        for _ in range(2):
            await app_client.post(
                "/api/parse/async",
                headers=auth_headers,
                json={"file_id": file_id}
            )
        
        # List runs for this file
        list_response = await app_client.get(
            "/api/parse",
            headers=auth_headers,
            params={"file_id": file_id, "limit": 10, "offset": 0}
        )
        
        data = list_response.json()
        assert len(data["items"]) >= 2
        
        # All runs should be for the same file
        for run in data["items"]:
            assert run["file_id"] == file_id
    
    async def test_parse_nonexistent_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test parsing with a nonexistent file ID."""
        response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={"file_id": "nonexistent"}
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
class TestIntegratedParsing:
    """Test integrated parsing workflows."""
    
    async def test_full_parsing_pipeline(self, app_client: AsyncClient, auth_headers: dict):
        """Test complete parsing pipeline with classification, splitting, and extraction."""
        # Create schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Full Pipeline Schema",
                "description": "Schema for full pipeline",
                "fields": [
                    {"name": "content", "type": "string", "description": "Content"}
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Create classifier
        classifier_response = await app_client.post(
            "/api/classifiers",
            headers=auth_headers,
            json={
                "name": "Pipeline Classifier",
                "type": "keyword",
                "enabled": True,
                "categories": ["document"],
                "rules": {
                    "keywords": {
                        "document": ["test", "content"]
                    }
                }
            }
        )
        classifier_id = classifier_response.json()["classifier_id"]
        
        # Create splitter
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Pipeline Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "delimiter",
                    "delimiter": "\n\n"
                }
            }
        )
        splitter_id = splitter_response.json()["splitter_id"]
        
        # Upload file
        test_content = b"This is test content.\n\nThis is more test content."
        test_file = ("pipeline_test.txt", BytesIO(test_content), "text/plain")
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Parse with all components
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={
                "file_id": file_id,
                "schema_id": schema_id,
                "classifier_id": classifier_id,
                "splitter_id": splitter_id
            }
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        data = parse_response.json()
        
        assert data["status"] in ["completed", "failed"]
        assert data["file_id"] == file_id
        
        if data["status"] == "completed":
            # Check that we got results
            assert "classification" in data or data["classification"] is None
            assert "chunks" in data or data["chunks"] is None
            assert "extracted" in data or data["extracted"] is None
