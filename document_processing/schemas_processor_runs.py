"""Schemas for processor runs with citations and confidence (Sprint 5 - P4.1)."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Citation with provenance for an extracted field.
    
    Citations link extracted data back to source locations in the document,
    providing transparency and verifiability.
    """
    
    page: int = Field(..., description="Page number (1-indexed)", ge=1)
    block_index: Optional[int] = Field(None, description="Index of text block on page")
    bbox: Optional[Dict[str, float]] = Field(
        None, 
        description="Bounding box: {x, y, width, height, page}"
    )
    text: Optional[str] = Field(None, description="Cited text snippet")
    confidence: Optional[float] = Field(
        None, 
        description="Confidence score for this citation (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "page": 1,
                "block_index": 3,
                "bbox": {"x": 72.0, "y": 150.0, "width": 200.0, "height": 20.0, "page": 1},
                "text": "Invoice Total: $1,234.56",
                "confidence": 0.95
            }
        }


class ExtractedField(BaseModel):
    """Extracted field with value, confidence, and citations."""
    
    name: str = Field(..., description="Field name from schema")
    value: Any = Field(..., description="Extracted value (string, number, array, object)")
    confidence: float = Field(
        ..., 
        description="Confidence score for extraction (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    citations: List[Citation] = Field(
        default_factory=list,
        description="Citations showing where value was found"
    )
    data_type: Optional[str] = Field(None, description="Type: string, number, date, etc.")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "invoice_total",
                "value": 1234.56,
                "confidence": 0.95,
                "citations": [
                    {
                        "page": 1,
                        "block_index": 5,
                        "text": "Total: $1,234.56",
                        "confidence": 0.95
                    }
                ],
                "data_type": "number"
            }
        }


class UsageMetrics(BaseModel):
    """Usage metrics for processor run."""
    
    input_tokens: Optional[int] = Field(None, description="Input tokens consumed")
    output_tokens: Optional[int] = Field(None, description="Output tokens generated")
    total_tokens: Optional[int] = Field(None, description="Total tokens (input + output)")
    processing_time_ms: Optional[int] = Field(None, description="Processing time in milliseconds")
    page_count: Optional[int] = Field(None, description="Number of pages processed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "input_tokens": 1500,
                "output_tokens": 300,
                "total_tokens": 1800,
                "processing_time_ms": 2500,
                "page_count": 3
            }
        }


class ProcessorRunData(BaseModel):
    """Enhanced processor run output with citations and confidence.
    
    This is the core data structure returned by processor runs,
    containing extracted fields with full provenance.
    """
    
    fields: List[ExtractedField] = Field(
        ...,
        description="Extracted fields with values, confidence, and citations"
    )
    overall_confidence: float = Field(
        ...,
        description="Overall confidence score for extraction (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    usage: Optional[UsageMetrics] = Field(None, description="Usage metrics")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "fields": [
                    {
                        "name": "invoice_number",
                        "value": "INV-2025-001",
                        "confidence": 0.98,
                        "citations": [{"page": 1, "text": "Invoice #INV-2025-001"}],
                        "data_type": "string"
                    },
                    {
                        "name": "total_amount",
                        "value": 1234.56,
                        "confidence": 0.95,
                        "citations": [{"page": 1, "text": "Total: $1,234.56"}],
                        "data_type": "number"
                    }
                ],
                "overall_confidence": 0.96,
                "usage": {
                    "input_tokens": 1500,
                    "output_tokens": 300,
                    "total_tokens": 1800,
                    "processing_time_ms": 2500,
                    "page_count": 3
                }
            }
        }


class ProcessorRunRequest(BaseModel):
    """Request to create a processor run."""
    
    file_id: Optional[str] = Field(None, description="ID of uploaded file to process")
    input_path: Optional[str] = Field(None, description="Path to input file (alternative to file_id)")
    processor_version_id: Optional[str] = Field(
        None, 
        description="Specific version to use (defaults to latest published)"
    )
    parameters: Optional[Dict[str, Any]] = Field(
        None,
        description="Processor-specific parameters"
    )
    webhook_url: Optional[str] = Field(None, description="Webhook URL for async notifications")
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "file_abc123",
                "processor_version_id": "pver_xyz789",
                "parameters": {
                    "confidence_threshold": 0.8
                }
            }
        }


class ProcessorRun(BaseModel):
    """Processor run response with enhanced output structure."""
    
    id: str = Field(..., description="Run ID", alias="runId")
    processor_id: str = Field(..., description="Processor ID", alias="processorId")
    processor_version_id: Optional[str] = Field(
        None, 
        description="Version ID used for this run",
        alias="processorVersionId"
    )
    version_number: Optional[int] = Field(
        None,
        description="Version number used",
        alias="versionNumber"
    )
    file_id: Optional[str] = Field(None, description="Input file ID", alias="fileId")
    status: str = Field(
        ..., 
        description="Status: queued, processing, completed, failed, cancelled"
    )
    
    # Enhanced output with citations
    data: Optional[ProcessorRunData] = Field(None, description="Extracted data with citations")
    
    # Error handling
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if failed")
    
    # API version tracking
    api_version: Optional[str] = Field(
        None,
        description="API version used for this run",
        alias="apiVersion"
    )
    
    # Timestamps
    created_at: datetime = Field(..., description="Creation timestamp", alias="createdAt")
    updated_at: datetime = Field(..., description="Last update timestamp", alias="updatedAt")
    started_at: Optional[datetime] = Field(None, description="Processing start time", alias="startedAt")
    completed_at: Optional[datetime] = Field(None, description="Completion time", alias="completedAt")
    
    # Tenant
    tenant_id: str = Field(..., description="Tenant ID", alias="tenantId")
    
    class Config:
        populate_by_name = True  # Allow both camelCase and snake_case
        json_schema_extra = {
            "example": {
                "runId": "run_abc123",
                "processorId": "proc_xyz789",
                "processorVersionId": "pver_v2",
                "versionNumber": 2,
                "fileId": "file_123",
                "status": "completed",
                "data": {
                    "fields": [
                        {
                            "name": "invoice_number",
                            "value": "INV-2025-001",
                            "confidence": 0.98,
                            "citations": [{"page": 1, "text": "Invoice #INV-2025-001"}]
                        }
                    ],
                    "overall_confidence": 0.96
                },
                "apiVersion": "2025-10-15",
                "createdAt": "2025-10-19T12:00:00Z",
                "updatedAt": "2025-10-19T12:00:05Z",
                "completedAt": "2025-10-19T12:00:05Z",
                "tenantId": "tenant_123"
            }
        }


class ProcessorRunListResponse(BaseModel):
    """Response for listing processor runs."""
    
    items: List[ProcessorRun] = Field(..., description="List of runs")
    meta: Dict[str, Any] = Field(
        default_factory=lambda: {"total": 0, "page": 1, "page_size": 50},
        description="Pagination metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "runId": "run_abc123",
                        "processorId": "proc_xyz789",
                        "status": "completed",
                        "createdAt": "2025-10-19T12:00:00Z",
                        "tenantId": "tenant_123"
                    }
                ],
                "meta": {
                    "total": 1,
                    "page": 1,
                    "page_size": 50
                }
            }
        }


class CancelProcessorRunRequest(BaseModel):
    """Request to cancel a processor run."""
    
    reason: Optional[str] = Field(None, description="Reason for cancellation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "reason": "User requested cancellation"
            }
        }
