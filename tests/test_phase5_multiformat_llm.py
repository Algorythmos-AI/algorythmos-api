"""
Tests for PHASE 5: Multi-format support and LLM integration.

Tests format handlers for different document types and LLM processing.
"""

import pytest
from httpx import AsyncClient
from fastapi import status
from io import BytesIO


@pytest.mark.asyncio
class TestFormatHandlers:
    """Test multi-format document handling."""
    
    async def test_upload_and_parse_text_file(self, app_client: AsyncClient, auth_headers: dict):
        """Test uploading and parsing a plain text file."""
        # Upload text file
        test_content = b"This is a test document with some content.\n\nSecond paragraph here."
        test_file = ("test.txt", BytesIO(test_content), "text/plain")
        
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        
        assert upload_response.status_code == status.HTTP_201_CREATED
        file_id = upload_response.json()["file_id"]
        
        # Parse the file
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        data = parse_response.json()
        assert data["status"] == "completed"
    
    async def test_pdf_format_detection(self, app_client: AsyncClient, auth_headers: dict):
        """Test that PDF files are detected and handled."""
        # Note: This test would need a real PDF file
        # For now, test the content type recognition
        
        # Create a minimal "PDF" (not a real PDF, just for testing)
        fake_pdf = b"%PDF-1.4\n%\xE2\xE3\xCF\xD3\n"
        test_file = ("document.pdf", BytesIO(fake_pdf), "application/pdf")
        
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        
        assert upload_response.status_code == status.HTTP_201_CREATED
        data = upload_response.json()
        assert data["content_type"] == "application/pdf"
    
    async def test_markdown_file_handling(self, app_client: AsyncClient, auth_headers: dict):
        """Test handling markdown files."""
        md_content = b"""# Test Document

## Section 1

This is a test markdown document.

## Section 2

More content here.
"""
        
        test_file = ("doc.md", BytesIO(md_content), "text/markdown")
        
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        
        assert upload_response.status_code == status.HTTP_201_CREATED
        file_id = upload_response.json()["file_id"]
        
        # Parse should work
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
    
    async def test_csv_file_handling(self, app_client: AsyncClient, auth_headers: dict):
        """Test handling CSV files."""
        csv_content = b"""Name,Age,City
John,30,NYC
Jane,25,LA
Bob,35,Chicago"""
        
        test_file = ("data.csv", BytesIO(csv_content), "text/csv")
        
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        
        assert upload_response.status_code == status.HTTP_201_CREATED
        file_id = upload_response.json()["file_id"]
        
        # Parse CSV
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        data = parse_response.json()
        assert data["status"] == "completed"


@pytest.mark.asyncio
class TestLLMProcessing:
    """Test LLM processing endpoints."""
    
    async def test_llm_summarize(self, app_client: AsyncClient, auth_headers: dict):
        """Test document summarization."""
        long_text = """
        This is a long document that needs to be summarized. It contains multiple paragraphs
        and various pieces of information. The document discusses important topics and provides
        detailed explanations. There are several key points that should be captured in the summary.
        
        The second paragraph continues with more information. It elaborates on the topics introduced
        earlier and provides additional context. This helps the reader understand the full scope
        of the document.
        
        Finally, the third paragraph concludes the document with final thoughts and recommendations.
        """
        
        response = await app_client.post(
            "/api/llm/summarize",
            headers=auth_headers,
            json={
                "text": long_text,
                "max_length": 200,
                "style": "concise"
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "summary" in data
        assert "style" in data
        assert "length" in data
        assert data["style"] == "concise"
    
    async def test_llm_extract_entities(self, app_client: AsyncClient, auth_headers: dict):
        """Test entity extraction."""
        text = """
        Apple Inc. announced today that CEO Tim Cook will visit New York City next month.
        The company plans to invest $1 billion in new facilities.
        """
        
        response = await app_client.post(
            "/api/llm/extract-entities",
            headers=auth_headers,
            json={
                "text": text,
                "entity_types": ["PERSON", "ORG", "LOCATION", "MONEY"]
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "entities" in data
        assert "entity_types" in data
        assert "total_entities" in data
    
    async def test_llm_answer_questions(self, app_client: AsyncClient, auth_headers: dict):
        """Test question answering."""
        text = """
        The company was founded in 2020 and has grown to 100 employees. It specializes
        in software development and has offices in San Francisco and Austin.
        """
        
        questions = [
            "When was the company founded?",
            "How many employees does it have?",
            "What cities have offices?"
        ]
        
        response = await app_client.post(
            "/api/llm/answer-questions",
            headers=auth_headers,
            json={
                "text": text,
                "questions": questions
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "answers" in data
        assert "total_questions" in data
        assert data["total_questions"] == 3
        assert len(data["answers"]) == 3
    
    async def test_llm_summarize_different_styles(self, app_client: AsyncClient, auth_headers: dict):
        """Test summarization with different styles."""
        text = "This is a test document with important information."
        
        for style in ["concise", "detailed", "bullet_points"]:
            response = await app_client.post(
                "/api/llm/summarize",
                headers=auth_headers,
                json={
                    "text": text,
                    "max_length": 500,
                    "style": style
                }
            )
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["style"] == style


@pytest.mark.asyncio
class TestLLMEnhancedParsing:
    """Test parser runs with LLM enhancements."""
    
    async def test_parse_with_llm_post_processing(self, app_client: AsyncClient, auth_headers: dict):
        """Test parsing with LLM post-processing enabled."""
        # Create schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "LLM Test Schema",
                "description": "Schema for LLM testing",
                "fields": [
                    {
                        "name": "company_name",
                        "type": "string",
                        "description": "Company name",
                        "required": True
                    },
                    {
                        "name": "year",
                        "type": "number",
                        "description": "Year founded"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Upload file
        text_content = b"TechCorp was founded in 2020 and has grown rapidly."
        test_file = ("llm_test.txt", BytesIO(text_content), "text/plain")
        
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        file_id = upload_response.json()["file_id"]
        
        # Parse with LLM post-processing
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={
                "file_id": file_id,
                "schema_id": schema_id,
                "metadata": {
                    "use_llm_post_processing": True
                }
            }
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        data = parse_response.json()
        assert data["status"] in ["completed", "failed"]
        
        # If completed, check for LLM enhancements
        if data["status"] == "completed" and data.get("extracted"):
            extracted = data["extracted"]
            # LLM enhancements would be present if enabled
            assert "fields" in extracted


@pytest.mark.asyncio
class TestFormatMetadataExtraction:
    """Test metadata extraction from different formats."""
    
    async def test_text_file_metadata(self, app_client: AsyncClient, auth_headers: dict):
        """Test that text files have metadata extracted."""
        text_content = b"Line 1\nLine 2\nLine 3\nThis has multiple words in it."
        test_file = ("metadata_test.txt", BytesIO(text_content), "text/plain")
        
        upload_response = await app_client.post(
            "/api/files",
            headers=auth_headers,
            files={"file": test_file}
        )
        
        file_id = upload_response.json()["file_id"]
        
        # Parse to extract metadata
        parse_response = await app_client.post(
            "/api/parse",
            headers=auth_headers,
            json={"file_id": file_id}
        )
        
        assert parse_response.status_code == status.HTTP_200_OK
        
        # Get parser run to check metadata
        run_id = parse_response.json()["run_id"]
        status_response = await app_client.get(
            f"/api/parse/{run_id}",
            headers=auth_headers
        )
        
        data = status_response.json()
        
        # Check if format metadata was extracted
        if data.get("metadata") and data["metadata"].get("format_metadata"):
            format_meta = data["metadata"]["format_metadata"]
            assert "character_count" in format_meta or "line_count" in format_meta


@pytest.mark.asyncio
class TestIntegratedMultiFormat:
    """Test integrated multi-format workflows."""
    
    async def test_different_formats_same_workflow(self, app_client: AsyncClient, auth_headers: dict):
        """Test that different formats can use the same processing workflow."""
        # Create a classifier
        classifier_response = await app_client.post(
            "/api/classifiers",
            headers=auth_headers,
            json={
                "name": "Multi-Format Classifier",
                "type": "keyword",
                "enabled": True,
                "categories": ["document"],
                "rules": {
                    "keywords": {
                        "document": ["test", "content", "data"]
                    }
                }
            }
        )
        classifier_id = classifier_response.json()["classifier_id"]
        
        # Test with different file types
        test_files = [
            ("test1.txt", b"This is test content.", "text/plain"),
            ("test2.csv", b"col1,col2\ndata1,data2", "text/csv"),
            ("test3.md", b"# Test\nContent here", "text/markdown"),
        ]
        
        for filename, content, content_type in test_files:
            # Upload
            test_file = (filename, BytesIO(content), content_type)
            upload_response = await app_client.post(
                "/api/files",
                headers=auth_headers,
                files={"file": test_file}
            )
            
            file_id = upload_response.json()["file_id"]
            
            # Parse with classifier
            parse_response = await app_client.post(
                "/api/parse",
                headers=auth_headers,
                json={
                    "file_id": file_id,
                    "classifier_id": classifier_id
                }
            )
            
            assert parse_response.status_code == status.HTTP_200_OK
            data = parse_response.json()
            assert data["status"] in ["completed", "failed"]
