"""
Sprint 3: Enhanced Parse API Schemas (P2.1)

Implements Extend API parity for parse results:
- Blocks structure (text, table, figure) with bounding boxes
- Chunks with metadata and provenance
- Page dimensions
- Timing metrics
- pageRanges support
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class BoundingBox(BaseModel):
    """Bounding box coordinates for content blocks."""
    
    x: float = Field(..., description="X coordinate (left)")
    y: float = Field(..., description="Y coordinate (top)")
    width: float = Field(..., description="Width of box")
    height: float = Field(..., description="Height of box")
    page: int = Field(..., description="Page number (1-indexed)")


class PageDimensions(BaseModel):
    """Page dimensions for layout context."""
    
    width: float = Field(..., description="Page width in points")
    height: float = Field(..., description="Page height in points")
    unit: str = Field(default="pt", description="Measurement unit")


class TextBlock(BaseModel):
    """Text content block with position."""
    
    type: Literal["text"] = "text"
    text: str = Field(..., description="Extracted text content")
    bbox: Optional[BoundingBox] = Field(None, description="Bounding box")
    confidence: Optional[float] = Field(None, description="Confidence score")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class TableBlock(BaseModel):
    """Table content block with structure."""
    
    type: Literal["table"] = "table"
    rows: List[List[str]] = Field(..., description="Table rows and cells")
    bbox: Optional[BoundingBox] = Field(None, description="Bounding box")
    confidence: Optional[float] = Field(None, description="Confidence score")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class FigureBlock(BaseModel):
    """Figure/image content block."""
    
    type: Literal["figure"] = "figure"
    caption: Optional[str] = Field(None, description="Figure caption")
    bbox: Optional[BoundingBox] = Field(None, description="Bounding box")
    confidence: Optional[float] = Field(None, description="Confidence score")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Image metadata")


# Union type for all block types
ContentBlock = TextBlock | TableBlock | FigureBlock


class Chunk(BaseModel):
    """Text chunk with metadata and provenance."""
    
    chunk_id: str = Field(..., description="Unique chunk identifier")
    text: str = Field(..., description="Chunk text content")
    page: Optional[int] = Field(None, description="Source page number")
    block_index: Optional[int] = Field(None, description="Source block index")
    start_char: Optional[int] = Field(None, description="Start character position")
    end_char: Optional[int] = Field(None, description="End character position")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Chunk metadata")


class ParseTiming(BaseModel):
    """Detailed timing metrics for parse operations."""
    
    total_ms: int = Field(..., description="Total processing time")
    format_detection_ms: Optional[int] = Field(None, description="Format detection time")
    text_extraction_ms: Optional[int] = Field(None, description="Text extraction time")
    classification_ms: Optional[int] = Field(None, description="Classification time")
    chunking_ms: Optional[int] = Field(None, description="Chunking time")
    extraction_ms: Optional[int] = Field(None, description="Data extraction time")


class EnhancedParseRequest(BaseModel):
    """Enhanced parse request with Extend API parameters."""
    
    file_id: str = Field(..., description="File to parse")
    
    # Format control
    target: Literal["json", "markdown", "text"] = Field(
        default="json",
        description="Output format target"
    )
    
    # Page selection
    page_ranges: Optional[str] = Field(
        None,
        description="Page ranges to process (e.g., '1-5,7,9-12')",
        alias="pageRanges"
    )
    
    # OCR options
    agentic_ocr: bool = Field(
        default=False,
        description="Enable advanced OCR processing",
        alias="agenticOcr"
    )
    
    page_rotation: Optional[int] = Field(
        None,
        description="Rotate pages by degrees (0, 90, 180, 270)",
        alias="pageRotation"
    )
    
    # Legacy fields (for backwards compatibility)
    schema_id: Optional[str] = None
    extractor_id: Optional[str] = None
    classifier_id: Optional[str] = None
    splitter_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        populate_by_name = True  # Allow both camelCase and snake_case


class EnhancedParseResult(BaseModel):
    """Enhanced parse result with Extend API structure."""
    
    # Identifiers
    run_id: str = Field(..., description="Parser run identifier")
    file_id: str = Field(..., description="File parsed")
    status: Literal["completed", "failed", "processing"] = Field(
        ..., description="Parse status"
    )
    
    # Structured content (Extend API format)
    blocks: Optional[List[ContentBlock]] = Field(
        None,
        description="Content blocks (text/table/figure) with positions"
    )
    
    chunks: Optional[List[Chunk]] = Field(
        None,
        description="Text chunks with provenance"
    )
    
    # Page information
    page_dimensions: Optional[Dict[int, PageDimensions]] = Field(
        None,
        description="Dimensions per page (1-indexed)"
    )
    
    pages_processed: Optional[int] = Field(
        None,
        description="Number of pages processed"
    )
    
    # Legacy fields (for backwards compatibility)
    classification: Optional[Dict[str, Any]] = Field(
        None, description="Classification result"
    )
    
    extracted: Optional[Dict[str, Any]] = Field(
        None, description="Extracted structured data"
    )
    
    # Quality metrics
    confidence: Optional[float] = Field(
        None,
        description="Overall confidence (0.0-1.0)"
    )
    
    # Timing
    timing: Optional[ParseTiming] = Field(
        None,
        description="Detailed timing metrics"
    )
    
    processing_time_ms: int = Field(
        ...,
        description="Total processing duration"
    )
    
    # Metadata
    completed_at: datetime = Field(..., description="Completion timestamp")
    api_version: Optional[str] = Field(None, description="API version used")
    
    # Errors
    error: Optional[str] = Field(None, description="Error message if failed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "file_id": "file_xyz789",
                "status": "completed",
                "blocks": [
                    {
                        "type": "text",
                        "text": "This is a sample paragraph.",
                        "bbox": {
                            "x": 72,
                            "y": 100,
                            "width": 400,
                            "height": 20,
                            "page": 1
                        },
                        "confidence": 0.98
                    }
                ],
                "chunks": [
                    {
                        "chunk_id": "chunk_1",
                        "text": "This is a sample paragraph.",
                        "page": 1,
                        "block_index": 0,
                        "metadata": {}
                    }
                ],
                "page_dimensions": {
                    "1": {"width": 612, "height": 792, "unit": "pt"}
                },
                "pages_processed": 1,
                "confidence": 0.98,
                "timing": {
                    "total_ms": 1500,
                    "format_detection_ms": 50,
                    "text_extraction_ms": 1200,
                    "chunking_ms": 250
                },
                "processing_time_ms": 1500,
                "completed_at": "2025-10-19T22:00:00Z"
            }
        }
