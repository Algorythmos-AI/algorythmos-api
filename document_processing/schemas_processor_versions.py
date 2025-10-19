"""Schemas for processor versioning (Sprint 4 - P3.1-P3.2)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateProcessorVersionRequest(BaseModel):
    """Request to create a new processor version.
    
    This creates a new version from an existing processor configuration.
    The version can be edited before being published.
    """
    
    processor_id: str = Field(..., description="ID of the processor to version")
    name: Optional[str] = Field(None, description="Optional name override for this version")
    description: Optional[str] = Field(None, description="Optional description for this version")
    implementation: Optional[Dict[str, Any]] = Field(None, description="Optional implementation override")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="Optional input schema override")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="Optional output schema override")
    change_notes: Optional[str] = Field(None, description="Notes about what changed in this version")
    
    class Config:
        json_schema_extra = {
            "example": {
                "processor_id": "proc_abc123",
                "change_notes": "Added support for multi-page documents"
            }
        }


class PublishProcessorVersionRequest(BaseModel):
    """Request to publish a processor version.
    
    Publishing makes a version immutable and available for use in production.
    """
    
    make_default: bool = Field(
        False, 
        description="Whether to make this the default version for the processor"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "make_default": True
            }
        }


class ProcessorVersion(BaseModel):
    """Response schema for a processor version."""
    
    id: str = Field(..., description="Unique version ID")
    processor_id: str = Field(..., description="Parent processor ID")
    version_number: int = Field(..., description="Sequential version number")
    name: str = Field(..., description="Version name")
    description: Optional[str] = Field(None, description="Version description")
    processor_type: str = Field(..., description="Type of processor")
    implementation: Dict[str, Any] = Field(..., description="Implementation details")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="Input schema")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="Output schema")
    
    # Version lifecycle
    status: str = Field(..., description="Version status: draft, published, deprecated")
    is_default: bool = Field(False, description="Whether this is the default version")
    published_at: Optional[datetime] = Field(None, description="When version was published")
    deprecated_at: Optional[datetime] = Field(None, description="When version was deprecated")
    
    # Change tracking
    change_notes: Optional[str] = Field(None, description="Notes about changes in this version")
    created_by: Optional[str] = Field(None, description="User who created this version")
    
    # Metadata
    tenant_id: str = Field(..., description="Tenant ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "pver_xyz789",
                "processor_id": "proc_abc123",
                "version_number": 2,
                "name": "Invoice Processor",
                "description": "Extracts invoice data",
                "processor_type": "extractor",
                "implementation": {"type": "llm", "model": "gpt-4"},
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "status": "published",
                "is_default": True,
                "published_at": "2025-10-19T12:00:00Z",
                "change_notes": "Added multi-page support",
                "tenant_id": "tenant_123",
                "created_at": "2025-10-19T10:00:00Z",
                "updated_at": "2025-10-19T12:00:00Z"
            }
        }


class ProcessorVersionListResponse(BaseModel):
    """Response for listing processor versions."""
    
    items: List[ProcessorVersion] = Field(..., description="List of versions")
    meta: Dict[str, Any] = Field(
        default_factory=lambda: {"total": 0, "page": 1, "page_size": 50},
        description="Pagination metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id": "pver_xyz789",
                        "processor_id": "proc_abc123",
                        "version_number": 2,
                        "name": "Invoice Processor v2",
                        "status": "published",
                        "is_default": True,
                        "created_at": "2025-10-19T10:00:00Z"
                    },
                    {
                        "id": "pver_xyz788",
                        "processor_id": "proc_abc123",
                        "version_number": 1,
                        "name": "Invoice Processor v1",
                        "status": "deprecated",
                        "is_default": False,
                        "created_at": "2025-10-18T10:00:00Z"
                    }
                ],
                "meta": {
                    "total": 2,
                    "page": 1,
                    "page_size": 50
                }
            }
        }


class ProcessorRunWithVersion(BaseModel):
    """Enhanced processor run that includes version information.
    
    Used in Sprint 5 to track which version was used for a run.
    """
    
    run_id: str = Field(..., description="Run ID")
    processor_id: str = Field(..., description="Processor ID")
    processor_version_id: Optional[str] = Field(None, description="Version ID used")
    version_number: Optional[int] = Field(None, description="Version number used")
    status: str = Field(..., description="Run status")
    api_version: Optional[str] = Field(None, description="API version header value")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_123",
                "processor_id": "proc_abc123",
                "processor_version_id": "pver_xyz789",
                "version_number": 2,
                "status": "completed",
                "api_version": "2025-10-15",
                "created_at": "2025-10-19T12:00:00Z"
            }
        }
