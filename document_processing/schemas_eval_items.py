"""
Evaluation Items Schemas (Sprint 7 - P6.1)

Schemas for bulk evaluation item creation.
Evaluation items are individual test cases within evaluation sets.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class EvalItemInput(BaseModel):
    """Single evaluation item for bulk creation."""
    
    id: Optional[str] = Field(None, description="Optional custom ID for the item")
    input_data: Dict[str, Any] = Field(..., description="Input data for the test case")
    expected_output: Dict[str, Any] = Field(..., description="Expected output/ground truth")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "test-001",
                    "input_data": {
                        "document_type": "invoice",
                        "file_url": "https://example.com/invoice.pdf"
                    },
                    "expected_output": {
                        "total_amount": 1000.00,
                        "invoice_number": "INV-2024-001"
                    },
                    "metadata": {
                        "category": "invoices",
                        "difficulty": "easy"
                    }
                }
            ]
        }
    }


class BulkItemError(BaseModel):
    """Error details for a failed item in bulk creation."""
    
    index: int = Field(..., description="Index of the failed item in the request")
    item_id: Optional[str] = Field(None, description="ID of the failed item (if provided)")
    error_type: str = Field(..., description="Error type (validation, duplicate, etc.)")
    message: str = Field(..., description="Human-readable error message")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "index": 2,
                    "item_id": "test-003",
                    "error_type": "duplicate",
                    "message": "Item with ID 'test-003' already exists"
                }
            ]
        }
    }


class BulkItemResult(BaseModel):
    """Result for a successfully created item."""
    
    id: str = Field(..., description="ID of the created item")
    index: int = Field(..., description="Index of the item in the request")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "item_a1b2c3d4e5f6",
                    "index": 0,
                    "created_at": "2024-01-19T10:30:00Z"
                }
            ]
        }
    }


class BulkCreateEvalItemsRequest(BaseModel):
    """Request to bulk create evaluation items."""
    
    evaluation_set_id: str = Field(
        ...,
        description="ID of the evaluation set to add items to",
        alias="evaluationSetId"
    )
    items: List[EvalItemInput] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of evaluation items to create (1-1000 items)"
    )
    
    @field_validator('items')
    @classmethod
    def validate_items(cls, v: List[EvalItemInput]) -> List[EvalItemInput]:
        """Validate that item IDs are unique if provided."""
        provided_ids = [item.id for item in v if item.id is not None]
        if len(provided_ids) != len(set(provided_ids)):
            raise ValueError("Duplicate item IDs found in request")
        return v
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "evaluation_set_id": "eval_1234567890ab",
                    "items": [
                        {
                            "id": "test-001",
                            "input_data": {"type": "invoice"},
                            "expected_output": {"amount": 1000.00}
                        },
                        {
                            "input_data": {"type": "receipt"},
                            "expected_output": {"amount": 50.00}
                        }
                    ]
                }
            ]
        }
    }


class BulkCreateEvalItemsResponse(BaseModel):
    """Response from bulk evaluation item creation."""
    
    evaluation_set_id: str = Field(
        ...,
        description="ID of the evaluation set",
        alias="evaluationSetId"
    )
    created_count: int = Field(
        ...,
        description="Number of items successfully created",
        alias="createdCount"
    )
    failed_count: int = Field(
        ...,
        description="Number of items that failed to create",
        alias="failedCount"
    )
    created_items: List[BulkItemResult] = Field(
        ...,
        description="List of successfully created items",
        alias="createdItems"
    )
    errors: List[BulkItemError] = Field(
        default_factory=list,
        description="List of errors for failed items"
    )
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "evaluation_set_id": "eval_1234567890ab",
                    "created_count": 2,
                    "failed_count": 0,
                    "created_items": [
                        {
                            "id": "item_a1b2c3d4e5f6",
                            "index": 0,
                            "created_at": "2024-01-19T10:30:00Z"
                        },
                        {
                            "id": "item_x9y8z7w6v5u4",
                            "index": 1,
                            "created_at": "2024-01-19T10:30:00Z"
                        }
                    ],
                    "errors": []
                }
            ]
        }
    }


class EvalItem(BaseModel):
    """Evaluation item response."""
    
    id: str = Field(..., description="Unique item identifier")
    evaluation_set_id: str = Field(
        ...,
        description="ID of the parent evaluation set",
        alias="evaluationSetId"
    )
    input_data: Dict[str, Any] = Field(..., description="Input data", alias="inputData")
    expected_output: Dict[str, Any] = Field(..., description="Expected output", alias="expectedOutput")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(..., description="Creation timestamp", alias="createdAt")
    updated_at: datetime = Field(..., description="Last update timestamp", alias="updatedAt")
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "item_a1b2c3d4e5f6",
                    "evaluation_set_id": "eval_1234567890ab",
                    "input_data": {"document_type": "invoice"},
                    "expected_output": {"total_amount": 1000.00},
                    "metadata": {"category": "invoices"},
                    "created_at": "2024-01-19T10:30:00Z",
                    "updated_at": "2024-01-19T10:30:00Z"
                }
            ]
        }
    }


class EvalItemListResponse(BaseModel):
    """Response for evaluation item list."""
    
    evaluation_set_id: str = Field(
        ...,
        description="ID of the evaluation set",
        alias="evaluationSetId"
    )
    items: List[EvalItem] = Field(..., description="List of evaluation items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(1, description="Current page number")
    page_size: int = Field(50, description="Number of items per page", alias="pageSize")
    
    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "evaluation_set_id": "eval_1234567890ab",
                    "items": [],
                    "total": 0,
                    "page": 1,
                    "page_size": 50
                }
            ]
        }
    }
