"""Schemas for workflow runs and corrections (Sprint 6 - P5.1-P5.2)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowStepResult(BaseModel):
    """Result from a single workflow step."""
    
    step_index: int = Field(..., description="Index of step in workflow", alias="stepIndex")
    processor_id: str = Field(..., description="Processor used", alias="processorId")
    processor_version_id: Optional[str] = Field(None, description="Version used", alias="processorVersionId")
    status: str = Field(..., description="Step status: completed, failed, skipped")
    data: Optional[Dict[str, Any]] = Field(None, description="Step output data")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if failed")
    processing_time_ms: Optional[int] = Field(None, description="Step duration", alias="processingTimeMs")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "stepIndex": 0,
                "processorId": "proc_extract",
                "processorVersionId": "pver_v1",
                "status": "completed",
                "data": {"invoice_number": "INV-001"},
                "processingTimeMs": 1500
            }
        }


class WorkflowRunRequest(BaseModel):
    """Request to create a workflow run."""
    
    file_id: Optional[str] = Field(None, description="ID of uploaded file to process", alias="fileId")
    input_path: Optional[str] = Field(None, description="Path to input file", alias="inputPath")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Workflow parameters")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for notifications", alias="webhookUrl")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "fileId": "file_abc123",
                "parameters": {
                    "confidence_threshold": 0.8
                }
            }
        }


class WorkflowRun(BaseModel):
    """Workflow run response."""
    
    id: str = Field(..., description="Run ID", alias="runId")
    workflow_id: str = Field(..., description="Workflow ID", alias="workflowId")
    file_id: Optional[str] = Field(None, description="Input file ID", alias="fileId")
    status: str = Field(
        ..., 
        description="Status: queued, processing, completed, failed, cancelled"
    )
    
    # Step results
    steps: List[WorkflowStepResult] = Field(
        default_factory=list,
        description="Results from each workflow step"
    )
    
    # Final output
    output: Optional[Dict[str, Any]] = Field(None, description="Final workflow output")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if failed")
    
    # API version tracking
    api_version: Optional[str] = Field(None, description="API version used", alias="apiVersion")
    
    # Timestamps
    created_at: datetime = Field(..., description="Creation timestamp", alias="createdAt")
    updated_at: datetime = Field(..., description="Last update timestamp", alias="updatedAt")
    started_at: Optional[datetime] = Field(None, description="Processing start time", alias="startedAt")
    completed_at: Optional[datetime] = Field(None, description="Completion time", alias="completedAt")
    
    # Tenant
    tenant_id: str = Field(..., description="Tenant ID", alias="tenantId")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "runId": "wfrun_abc123",
                "workflowId": "wf_xyz789",
                "fileId": "file_123",
                "status": "completed",
                "steps": [
                    {
                        "stepIndex": 0,
                        "processorId": "proc_extract",
                        "status": "completed",
                        "data": {"invoice_number": "INV-001"}
                    },
                    {
                        "stepIndex": 1,
                        "processorId": "proc_validate",
                        "status": "completed",
                        "data": {"is_valid": True}
                    }
                ],
                "output": {"invoice_number": "INV-001", "is_valid": True},
                "apiVersion": "2025-10-15",
                "createdAt": "2025-10-19T12:00:00Z",
                "updatedAt": "2025-10-19T12:00:05Z",
                "completedAt": "2025-10-19T12:00:05Z",
                "tenantId": "tenant_123"
            }
        }


class WorkflowRunListResponse(BaseModel):
    """Response for listing workflow runs."""
    
    items: List[WorkflowRun] = Field(..., description="List of runs")
    meta: Dict[str, Any] = Field(
        default_factory=lambda: {"total": 0, "page": 1, "page_size": 50},
        description="Pagination metadata"
    )


class FieldCorrection(BaseModel):
    """Correction for a specific field."""
    
    field_name: str = Field(..., description="Name of field to correct", alias="fieldName")
    original_value: Any = Field(..., description="Original extracted value", alias="originalValue")
    corrected_value: Any = Field(..., description="Corrected value", alias="correctedValue")
    reason: Optional[str] = Field(None, description="Reason for correction")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "fieldName": "invoice_total",
                "originalValue": 1234.56,
                "correctedValue": 1234.57,
                "reason": "OCR misread decimal"
            }
        }


class CorrectWorkflowRunRequest(BaseModel):
    """Request to submit corrections for a workflow run.
    
    Corrections are used to improve model accuracy through feedback loops.
    They can trigger retraining or adjustment of confidence thresholds.
    """
    
    corrections: List[FieldCorrection] = Field(
        ...,
        description="List of field corrections",
        min_length=1
    )
    notes: Optional[str] = Field(None, description="Additional notes about corrections")
    apply_immediately: bool = Field(
        False,
        description="Whether to apply corrections and reprocess",
        alias="applyImmediately"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "corrections": [
                    {
                        "fieldName": "invoice_total",
                        "originalValue": 1234.56,
                        "correctedValue": 1234.57,
                        "reason": "OCR misread decimal"
                    },
                    {
                        "fieldName": "vendor_name",
                        "originalValue": "Acme Corp",
                        "correctedValue": "Acme Corporation",
                        "reason": "Standardized company name"
                    }
                ],
                "notes": "Fixed OCR errors and standardized names",
                "applyImmediately": False
            }
        }


class CorrectionResult(BaseModel):
    """Result of applying corrections."""
    
    run_id: str = Field(..., description="Workflow run ID", alias="runId")
    corrections_applied: int = Field(..., description="Number of corrections applied", alias="correctionsApplied")
    status: str = Field(..., description="Status: accepted, reprocessing, completed")
    reprocessed_output: Optional[Dict[str, Any]] = Field(
        None,
        description="New output if reprocessed",
        alias="reprocessedOutput"
    )
    message: str = Field(..., description="Result message")
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "runId": "wfrun_abc123",
                "correctionsApplied": 2,
                "status": "accepted",
                "message": "Corrections stored for future model improvement"
            }
        }


class CancelWorkflowRunRequest(BaseModel):
    """Request to cancel a workflow run."""
    
    reason: Optional[str] = Field(None, description="Reason for cancellation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "reason": "User requested cancellation"
            }
        }


class WorkflowRunWithCorrections(BaseModel):
    """Workflow run including correction history."""
    
    run: WorkflowRun = Field(..., description="Workflow run details")
    corrections: List[FieldCorrection] = Field(
        default_factory=list,
        description="Corrections submitted for this run"
    )
    correction_count: int = Field(0, description="Total number of corrections", alias="correctionCount")
    last_corrected_at: Optional[datetime] = Field(
        None,
        description="When last correction was submitted",
        alias="lastCorrectedAt"
    )
    
    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "run": {
                    "runId": "wfrun_abc123",
                    "workflowId": "wf_xyz789",
                    "status": "completed",
                    "createdAt": "2025-10-19T12:00:00Z",
                    "tenantId": "t1"
                },
                "corrections": [
                    {
                        "fieldName": "invoice_total",
                        "originalValue": 1234.56,
                        "correctedValue": 1234.57,
                        "reason": "OCR error"
                    }
                ],
                "correctionCount": 1,
                "lastCorrectedAt": "2025-10-19T13:00:00Z"
            }
        }
