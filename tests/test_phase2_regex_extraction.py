"""
Tests for PHASE 2: Regex-based extraction.

Tests the regex extraction service and POST /extract/regex endpoint.
"""

import pytest
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
class TestRegexExtraction:
    """Test regex extraction functionality."""
    
    async def test_extract_with_regex_basic(self, app_client: AsyncClient, auth_headers: dict):
        """Test basic regex extraction with a simple schema."""
        # Create a schema with regex patterns
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Invoice Extraction Schema",
                "description": "Extract invoice fields",
                "fields": [
                    {
                        "name": "invoice_number",
                        "type": "string",
                        "required": True,
                        "description": "Invoice number",
                        "pattern": r"Invoice\s+#\s*([A-Z0-9-]+)"
                    },
                    {
                        "name": "total_amount",
                        "type": "number",
                        "required": True,
                        "description": "Total amount",
                        "pattern": r"Total:\s*\$\s*(\d+(?:\.\d{2})?)"
                    },
                    {
                        "name": "email",
                        "type": "string",
                        "required": False,
                        "description": "Email address"
                    }
                ]
            }
        )
        
        assert schema_response.status_code == status.HTTP_201_CREATED
        schema_id = schema_response.json()["schema_id"]
        
        # Test text with invoice data
        test_text = """
        INVOICE
        
        Invoice # INV-2024-001
        Date: 2024-10-19
        
        Items:
        - Product A: $50.00
        - Product B: $30.50
        
        Total: $ 80.50
        
        Contact: billing@example.com
        """
        
        # Perform extraction
        extract_response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": schema_id,
                "text": test_text
            }
        )
        
        assert extract_response.status_code == status.HTTP_200_OK
        result = extract_response.json()
        
        # Verify response structure
        assert "schema_id" in result
        assert "schema_name" in result
        assert "extracted_fields" in result
        assert "extracted_count" in result
        assert "total_fields" in result
        
        # Verify extraction results
        assert result["schema_id"] == schema_id
        assert result["schema_name"] == "Invoice Extraction Schema"
        assert result["extracted_count"] >= 2  # At least invoice number and total
        
        # Find specific fields
        extracted_fields = {f["field_name"]: f for f in result["extracted_fields"]}
        
        # Check invoice number
        assert "invoice_number" in extracted_fields
        assert extracted_fields["invoice_number"]["value"] == "INV-2024-001"
        assert extracted_fields["invoice_number"]["confidence"] > 0.5
        assert "citation" in extracted_fields["invoice_number"]
        
        # Check total amount
        assert "total_amount" in extracted_fields
        assert float(extracted_fields["total_amount"]["value"]) == 80.50
        assert extracted_fields["total_amount"]["confidence"] > 0.5
        
        # Check email (auto-detected pattern)
        assert "email" in extracted_fields
        assert extracted_fields["email"]["value"] == "billing@example.com"
    
    async def test_extract_with_nonexistent_schema(self, app_client: AsyncClient, auth_headers: dict):
        """Test extraction with nonexistent schema returns 404."""
        response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": "nonexistent_schema_id",
                "text": "Some text"
            }
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        error = response.json()
        assert "error" in error
        assert error["error"]["type"] == "resource_not_found"
    
    async def test_extract_with_extractor_config(self, app_client: AsyncClient, auth_headers: dict):
        """Test extraction using a specific extractor configuration."""
        # Create schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Email Schema",
                "description": "Extract email addresses",
                "fields": [
                    {
                        "name": "primary_email",
                        "type": "string",
                        "required": True,
                        "description": "Primary email address"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Create extractor with custom pattern
        extractor_response = await app_client.post(
            "/api/extractors",
            headers=auth_headers,
            json={
                "name": "Custom Email Extractor",
                "type": "regex",
                "schema_id": schema_id,
                "enabled": True,
                "priority": 1,
                "rules": {
                    "patterns": {
                        "primary_email": r"Primary:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
                    }
                }
            }
        )
        extractor_id = extractor_response.json()["extractor_id"]
        
        # Test text
        test_text = "Primary: admin@company.com\nSecondary: support@company.com"
        
        # Extract with custom extractor
        extract_response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": schema_id,
                "text": test_text,
                "extractor_id": extractor_id
            }
        )
        
        assert extract_response.status_code == status.HTTP_200_OK
        result = extract_response.json()
        
        # Should extract using custom pattern
        assert result["extractor_id"] == extractor_id
        assert result["extracted_count"] == 1
        
        extracted = result["extracted_fields"][0]
        assert extracted["field_name"] == "primary_email"
        assert extracted["value"] == "admin@company.com"
    
    async def test_extract_citations(self, app_client: AsyncClient, auth_headers: dict):
        """Test that extractions include proper citations."""
        # Create schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Citation Test Schema",
                "description": "Test citations",
                "fields": [
                    {
                        "name": "order_id",
                        "type": "string",
                        "required": True,
                        "pattern": r"Order\s+ID:\s*([A-Z0-9]+)"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Extract
        test_text = "Your Order ID: ABC123 has been shipped."
        extract_response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": schema_id,
                "text": test_text
            }
        )
        
        assert extract_response.status_code == status.HTTP_200_OK
        result = extract_response.json()
        
        # Check citation
        extracted = result["extracted_fields"][0]
        citation = extracted["citation"]
        
        assert "start_pos" in citation
        assert "end_pos" in citation
        assert "matched_text" in citation
        assert "pattern" in citation
        
        # Verify citation points to correct location
        assert citation["start_pos"] >= 0
        assert citation["end_pos"] > citation["start_pos"]
        assert "Order ID: ABC123" in citation["matched_text"]
    
    async def test_extract_no_matches(self, app_client: AsyncClient, auth_headers: dict):
        """Test extraction when no patterns match."""
        # Create schema
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "No Match Schema",
                "description": "Will not match",
                "fields": [
                    {
                        "name": "special_code",
                        "type": "string",
                        "required": True,
                        "pattern": r"CODE-\d{10}"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        # Extract from text without the pattern
        test_text = "This text has no special codes."
        extract_response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": schema_id,
                "text": test_text
            }
        )
        
        assert extract_response.status_code == status.HTTP_200_OK
        result = extract_response.json()
        
        # Should return successfully with 0 extractions
        assert result["extracted_count"] == 0
        assert len(result["extracted_fields"]) == 0
        assert result["total_fields"] == 1


@pytest.mark.asyncio
class TestAutoPatternDetection:
    """Test automatic pattern detection for common field types."""
    
    async def test_auto_detect_email(self, app_client: AsyncClient, auth_headers: dict):
        """Test automatic email pattern detection."""
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Auto Email Schema",
                "description": "Auto-detect email",
                "fields": [
                    {
                        "name": "contact_email",
                        "type": "string",
                        "required": False,
                        "description": "Contact email address"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        test_text = "Contact us at: john.doe@example.com for more info."
        extract_response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": schema_id,
                "text": test_text
            }
        )
        
        result = extract_response.json()
        assert result["extracted_count"] == 1
        assert result["extracted_fields"][0]["value"] == "john.doe@example.com"
    
    async def test_auto_detect_phone(self, app_client: AsyncClient, auth_headers: dict):
        """Test automatic phone number pattern detection."""
        schema_response = await app_client.post(
            "/api/schemas",
            headers=auth_headers,
            json={
                "name": "Auto Phone Schema",
                "description": "Auto-detect phone",
                "fields": [
                    {
                        "name": "phone_number",
                        "type": "string",
                        "required": False,
                        "description": "Phone number"
                    }
                ]
            }
        )
        schema_id = schema_response.json()["schema_id"]
        
        test_text = "Call us at 555-123-4567 today!"
        extract_response = await app_client.post(
            "/api/extract/regex",
            headers=auth_headers,
            json={
                "schema_id": schema_id,
                "text": test_text
            }
        )
        
        result = extract_response.json()
        assert result["extracted_count"] == 1
        assert "555" in result["extracted_fields"][0]["value"]
