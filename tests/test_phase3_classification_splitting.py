"""
Tests for PHASE 3: Document classification and splitting.

Tests the classification and splitting services and endpoints.
"""

import pytest
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
class TestDocumentClassification:
    """Test document classification functionality."""
    
    async def test_classify_with_keywords(self, app_client: AsyncClient, auth_headers: dict):
        """Test classification using keyword matching."""
        # Create a classifier
        classifier_response = await app_client.post(
            "/api/classifiers",
            headers=auth_headers,
            json={
                "name": "Document Type Classifier",
                "type": "keyword",
                "enabled": True,
                "categories": ["invoice", "receipt", "contract"],
                "rules": {
                    "keywords": {
                        "invoice": ["invoice", "bill", "payment due"],
                        "receipt": ["receipt", "purchased", "transaction"],
                        "contract": ["agreement", "terms and conditions", "signatory"]
                    }
                }
            }
        )
        
        assert classifier_response.status_code == status.HTTP_201_CREATED
        classifier_id = classifier_response.json()["classifier_id"]
        
        # Test invoice text
        invoice_text = """
        INVOICE
        
        Invoice Number: INV-2024-001
        Payment Due: 2024-11-01
        
        Please remit payment to the address below.
        """
        
        classify_response = await app_client.post(
            "/api/classify",
            headers=auth_headers,
            json={
                "text": invoice_text,
                "classifier_id": classifier_id
            }
        )
        
        assert classify_response.status_code == status.HTTP_200_OK
        result = classify_response.json()
        
        # Verify response structure
        assert "classifications" in result
        assert "top_category" in result
        assert "classifiers_used" in result
        
        # Should classify as invoice
        assert result["top_category"] == "invoice"
        assert len(result["classifications"]) > 0
        
        # Check first classification
        top_classification = result["classifications"][0]
        assert top_classification["category"] == "invoice"
        assert top_classification["confidence"] > 0.5
        assert "matched_keywords" in top_classification
        assert "invoice" in [k.lower() for k in top_classification["matched_keywords"]]
    
    async def test_classify_multiple_categories(self, app_client: AsyncClient, auth_headers: dict):
        """Test classification matching multiple categories."""
        # Create classifier
        classifier_response = await app_client.post(
            "/api/classifiers",
            headers=auth_headers,
            json={
                "name": "Multi-Category Classifier",
                "type": "keyword",
                "enabled": True,
                "categories": ["financial", "legal"],
                "rules": {
                    "keywords": {
                        "financial": ["payment", "invoice", "transaction"],
                        "legal": ["agreement", "contract", "terms"]
                    }
                }
            }
        )
        classifier_id = classifier_response.json()["classifier_id"]
        
        # Text matching both categories
        mixed_text = "This is a payment agreement with contract terms and invoice details."
        
        classify_response = await app_client.post(
            "/api/classify",
            headers=auth_headers,
            json={
                "text": mixed_text,
                "classifier_id": classifier_id
            }
        )
        
        result = classify_response.json()
        
        # Should have classifications for both categories
        categories_found = [c["category"] for c in result["classifications"]]
        assert "financial" in categories_found
        assert "legal" in categories_found
        
        # Results should be ordered by confidence
        confidences = [c["confidence"] for c in result["classifications"]]
        assert confidences == sorted(confidences, reverse=True)
    
    async def test_classify_no_classifier(self, app_client: AsyncClient, auth_headers: dict):
        """Test classification without any enabled classifiers."""
        response = await app_client.post(
            "/api/classify",
            headers=auth_headers,
            json={
                "text": "Some text to classify"
            }
        )
        
        # Should return 404 if no classifiers available
        assert response.status_code == status.HTTP_404_NOT_FOUND
        error = response.json()
        assert "error" in error
        assert error["error"]["type"] == "resource_not_found"
    
    async def test_classify_nonexistent_classifier(self, app_client: AsyncClient, auth_headers: dict):
        """Test classification with nonexistent classifier ID."""
        response = await app_client.post(
            "/api/classify",
            headers=auth_headers,
            json={
                "text": "Some text",
                "classifier_id": "nonexistent_id"
            }
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
class TestDocumentSplitting:
    """Test document splitting functionality."""
    
    async def test_split_by_delimiter(self, app_client: AsyncClient, auth_headers: dict):
        """Test splitting by delimiter."""
        # Create a delimiter-based splitter
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Paragraph Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "delimiter",
                    "delimiter": "\n\n"
                }
            }
        )
        
        assert splitter_response.status_code == status.HTTP_201_CREATED
        splitter_id = splitter_response.json()["splitter_id"]
        
        # Test text with paragraphs
        test_text = """First paragraph.
This is still the first paragraph.

Second paragraph here.

Third and final paragraph."""
        
        split_response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={
                "text": test_text,
                "splitter_id": splitter_id
            }
        )
        
        assert split_response.status_code == status.HTTP_200_OK
        result = split_response.json()
        
        # Verify response structure
        assert "splitter_id" in result
        assert "split_strategy" in result
        assert "chunks" in result
        assert "chunk_count" in result
        
        # Should have 3 chunks
        assert result["chunk_count"] == 3
        assert len(result["chunks"]) == 3
        
        # Verify chunk structure
        for i, chunk in enumerate(result["chunks"]):
            assert "content" in chunk
            assert "chunk_index" in chunk
            assert "start_pos" in chunk
            assert "end_pos" in chunk
            assert "metadata" in chunk
            assert chunk["chunk_index"] == i
    
    async def test_split_by_pattern(self, app_client: AsyncClient, auth_headers: dict):
        """Test splitting by regex pattern."""
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Section Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "pattern",
                    "pattern": r"===\s*SECTION\s*==="
                }
            }
        )
        splitter_id = splitter_response.json()["splitter_id"]
        
        test_text = """Content of section 1.
=== SECTION ===
Content of section 2.
=== SECTION ===
Content of section 3."""
        
        split_response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={
                "text": test_text,
                "splitter_id": splitter_id
            }
        )
        
        result = split_response.json()
        
        # Should split into 3 sections
        assert result["chunk_count"] == 3
        assert result["split_strategy"] == "pattern"
    
    async def test_split_fixed_size(self, app_client: AsyncClient, auth_headers: dict):
        """Test splitting by fixed size."""
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Fixed Size Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "fixed_size",
                    "chunk_size": 50,
                    "overlap": 10
                }
            }
        )
        splitter_id = splitter_response.json()["splitter_id"]
        
        # Create long text
        test_text = "A" * 150  # 150 characters
        
        split_response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={
                "text": test_text,
                "splitter_id": splitter_id
            }
        )
        
        result = split_response.json()
        
        # Should create multiple chunks
        assert result["chunk_count"] >= 3
        assert result["split_strategy"] == "fixed_size"
        
        # Verify chunks have correct sizes
        for chunk in result["chunks"]:
            assert len(chunk["content"]) <= 50
    
    async def test_split_by_paragraph(self, app_client: AsyncClient, auth_headers: dict):
        """Test splitting by paragraph."""
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Paragraph Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "paragraph"
                }
            }
        )
        splitter_id = splitter_response.json()["splitter_id"]
        
        test_text = """First paragraph.


Second paragraph.


Third paragraph."""
        
        split_response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={
                "text": test_text,
                "splitter_id": splitter_id
            }
        )
        
        result = split_response.json()
        
        assert result["chunk_count"] == 3
        assert result["split_strategy"] == "paragraph"
    
    async def test_split_no_splitter(self, app_client: AsyncClient, auth_headers: dict):
        """Test splitting without any enabled splitters."""
        response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={
                "text": "Some text to split"
            }
        )
        
        # Should return 404 if no splitters available
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_split_chunk_metadata(self, app_client: AsyncClient, auth_headers: dict):
        """Test that chunks include proper metadata."""
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Metadata Test Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "delimiter",
                    "delimiter": "---"
                }
            }
        )
        splitter_id = splitter_response.json()["splitter_id"]
        
        test_text = "Part 1---Part 2---Part 3"
        
        split_response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={
                "text": test_text,
                "splitter_id": splitter_id
            }
        )
        
        result = split_response.json()
        
        # Verify each chunk has metadata
        for chunk in result["chunks"]:
            assert "metadata" in chunk
            assert "split_type" in chunk["metadata"]
            assert chunk["metadata"]["split_type"] == "delimiter"


@pytest.mark.asyncio
class TestIntegrationWorkflow:
    """Test integrated classification and splitting workflow."""
    
    async def test_classify_then_split(self, app_client: AsyncClient, auth_headers: dict):
        """Test classifying a document then splitting it."""
        # Create classifier
        classifier_response = await app_client.post(
            "/api/classifiers",
            headers=auth_headers,
            json={
                "name": "Doc Classifier",
                "type": "keyword",
                "enabled": True,
                "categories": ["report"],
                "rules": {
                    "keywords": {
                        "report": ["report", "summary", "findings"]
                    }
                }
            }
        )
        
        # Create splitter
        splitter_response = await app_client.post(
            "/api/splitters",
            headers=auth_headers,
            json={
                "name": "Section Splitter",
                "type": "rule_based",
                "enabled": True,
                "rules": {
                    "strategy": "delimiter",
                    "delimiter": "\n\n"
                }
            }
        )
        
        test_text = """REPORT SUMMARY

First section with findings.

Second section with more details.

Final conclusions."""
        
        # Classify
        classify_response = await app_client.post(
            "/api/classify",
            headers=auth_headers,
            json={"text": test_text}
        )
        
        assert classify_response.status_code == status.HTTP_200_OK
        classification = classify_response.json()
        assert classification["top_category"] == "report"
        
        # Split
        split_response = await app_client.post(
            "/api/split",
            headers=auth_headers,
            json={"text": test_text}
        )
        
        assert split_response.status_code == status.HTTP_200_OK
        splitting = split_response.json()
        assert splitting["chunk_count"] >= 3
