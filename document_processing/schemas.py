"""Pydantic schemas for generic document processing."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class FieldDefinition(BaseModel):
    """Definition of a single extraction field."""
    
    name: str = Field(..., description="Field name (e.g., 'invoice_number', 'total_amount')")
    type: Literal["string", "number", "date", "boolean", "array", "object"] = Field(
        ..., description="Data type of the field"
    )
    description: Optional[str] = Field(None, description="Human-readable description")
    required: bool = Field(False, description="Whether this field is required")
    default: Optional[Any] = Field(None, description="Default value if not extracted")
    validation: Optional[Dict[str, Any]] = Field(
        None,
        description="Validation rules (e.g., {'min': 0, 'max': 100, 'pattern': '^[A-Z]'})"
    )
    
    @field_validator('name')
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        """Ensure field name is a valid identifier."""
        if not v.replace('_', '').isalnum():
            raise ValueError(f"Field name '{v}' must be alphanumeric with underscores only")
        if v.startswith('_'):
            raise ValueError(f"Field name '{v}' cannot start with underscore")
        return v.lower()


class ExtractionSchema(BaseModel):
    """Schema defining what fields to extract from documents."""
    
    schema_id: str = Field(..., description="Unique schema identifier")
    name: str = Field(..., description="Human-readable schema name")
    description: str = Field(..., description="What this schema extracts")
    fields: List[FieldDefinition] = Field(..., description="List of fields to extract")
    version: int = Field(1, description="Schema version for evolution")
    tenant_id: str = Field(..., description="Owner tenant ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @field_validator('fields')
    @classmethod
    def validate_unique_field_names(cls, v: List[FieldDefinition]) -> List[FieldDefinition]:
        """Ensure all field names are unique."""
        names = [f.name for f in v]
        if len(names) != len(set(names)):
            duplicates = [name for name in names if names.count(name) > 1]
            raise ValueError(f"Duplicate field names: {duplicates}")
        return v


class CreateSchemaRequest(BaseModel):
    """Request to create a new extraction schema."""
    
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    fields: List[FieldDefinition] = Field(..., min_items=1, max_items=100)
    metadata: Optional[Dict[str, Any]] = None


class UpdateSchemaRequest(BaseModel):
    """Request to update an existing schema."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    fields: Optional[List[FieldDefinition]] = Field(None, min_items=1, max_items=100)
    metadata: Optional[Dict[str, Any]] = None


class SchemaListResponse(BaseModel):
    """Response for listing schemas with pagination."""
    
    items: List[ExtractionSchema]
    total: int
    limit: int
    cursor: Optional[str] = None
    has_more: bool


class ExtractorConfig(BaseModel):
    """Configuration for a custom extractor."""
    
    extractor_id: str = Field(..., description="Unique extractor identifier")
    name: str = Field(..., description="Human-readable extractor name")
    type: Literal["regex", "llm", "template", "ml", "rule_based"] = Field(
        ..., description="Type of extraction engine"
    )
    schema_id: str = Field(..., description="Schema this extractor uses")
    tenant_id: str = Field(..., description="Owner tenant ID")
    enabled: bool = Field(True, description="Whether extractor is active")
    priority: int = Field(100, description="Execution priority (lower = higher priority)")
    rules: Dict[str, Any] = Field(
        ...,
        description="Type-specific extraction rules"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateExtractorRequest(BaseModel):
    """Request to create a new extractor."""
    
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["regex", "llm", "template", "ml", "rule_based"]
    schema_id: str = Field(..., description="ID of schema to use")
    rules: Dict[str, Any] = Field(..., description="Extraction rules configuration")
    enabled: bool = Field(True)
    priority: int = Field(100, ge=0, le=1000)


class UpdateExtractorRequest(BaseModel):
    """Request to update an extractor."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(None, ge=0, le=1000)
    rules: Optional[Dict[str, Any]] = None


class ClassifierConfig(BaseModel):
    """Configuration for a document classifier."""
    
    classifier_id: str
    name: str
    type: Literal["keyword", "ml", "llm", "rule_based"]
    tenant_id: str
    enabled: bool = True
    categories: List[str] = Field(..., description="Possible classification categories")
    rules: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateClassifierRequest(BaseModel):
    """Request to create a new classifier."""
    
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["keyword", "ml", "llm", "rule_based"]
    categories: List[str] = Field(..., min_items=1, description="Classification categories")
    rules: Dict[str, Any] = Field(..., description="Classification rules configuration")
    enabled: bool = Field(True)


class UpdateClassifierRequest(BaseModel):
    """Request to update a classifier."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    enabled: Optional[bool] = None
    categories: Optional[List[str]] = Field(None, min_items=1)
    rules: Optional[Dict[str, Any]] = None


class ClassificationResult(BaseModel):
    """Result from document classification."""
    
    category: str = Field(..., description="Primary category")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    subcategories: Optional[List[str]] = Field(None, description="Additional categories")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SplitterConfig(BaseModel):
    """Configuration for a document splitter."""
    
    splitter_id: str
    name: str
    type: Literal["page", "section", "pattern", "size"]
    tenant_id: str
    enabled: bool = True
    rules: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreateSplitterRequest(BaseModel):
    """Request to create a new splitter."""
    
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["page", "section", "pattern", "size"]
    rules: Dict[str, Any] = Field(..., description="Splitter rules configuration")
    enabled: bool = Field(True)


class UpdateSplitterRequest(BaseModel):
    """Request to update a splitter."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    enabled: Optional[bool] = None
    rules: Optional[Dict[str, Any]] = None


class DocumentChunk(BaseModel):
    """A chunk from a split document."""
    
    chunk_id: str
    parent_document_id: str
    chunk_index: int
    page_range: Optional[tuple[int, int]] = None
    content_type: str = Field(default="application/pdf")
    content_size: int = Field(..., description="Size in bytes")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Citation(BaseModel):
    """Citation showing where extracted data came from."""
    
    field_name: str
    source_page: Optional[int] = None
    source_text: str = Field(..., description="The actual text that was extracted")
    bbox: Optional[tuple[float, float, float, float]] = Field(
        None, description="Bounding box (x1, y1, x2, y2)"
    )
    extraction_method: Literal["regex", "llm", "template", "manual", "rule_based"]
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedField(BaseModel):
    """A single extracted field with citation."""
    
    name: str
    value: Any
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: List[Citation] = Field(default_factory=list)


class GenericExtractionResult(BaseModel):
    """Result from generic document extraction."""
    
    document_id: str
    schema_id: str
    schema_name: str
    extractor_id: str
    fields: List[ExtractedField]
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)
    processing_time_ms: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Rebuild models to resolve forward references
FieldDefinition.model_rebuild()
ExtractionSchema.model_rebuild()
CreateSchemaRequest.model_rebuild()
UpdateSchemaRequest.model_rebuild()
SchemaListResponse.model_rebuild()
ExtractorConfig.model_rebuild()
CreateExtractorRequest.model_rebuild()
UpdateExtractorRequest.model_rebuild()
ClassifierConfig.model_rebuild()
CreateClassifierRequest.model_rebuild()
UpdateClassifierRequest.model_rebuild()
ClassificationResult.model_rebuild()
SplitterConfig.model_rebuild()
CreateSplitterRequest.model_rebuild()
UpdateSplitterRequest.model_rebuild()
DocumentChunk.model_rebuild()
Citation.model_rebuild()
ExtractedField.model_rebuild()
GenericExtractionResult.model_rebuild()


# =============================================================================
# PHASE 4: File and Parser Run Schemas
# =============================================================================


class FileUpload(BaseModel):
    """Response for uploaded file."""
    
    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type")
    size_bytes: int = Field(..., description="File size in bytes")
    checksum: str = Field(..., description="SHA-256 checksum")
    tenant_id: str = Field(..., description="Owner tenant ID")
    created_at: datetime = Field(..., description="Upload timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ParserRunRequest(BaseModel):
    """Request to create a parser run."""
    
    file_id: str = Field(..., description="File to parse")
    schema_id: Optional[str] = Field(None, description="Extraction schema to use")
    extractor_id: Optional[str] = Field(None, description="Extractor to use")
    classifier_id: Optional[str] = Field(None, description="Classifier to use")
    splitter_id: Optional[str] = Field(None, description="Splitter to use")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional run metadata")


class ParserRunStatus(BaseModel):
    """Status of a parser run."""
    
    run_id: str = Field(..., description="Unique run identifier")
    file_id: str = Field(..., description="File being parsed")
    status: Literal["pending", "running", "completed", "failed", "dead_letter"] = Field(
        ..., description="Current status"
    )
    tenant_id: str = Field(..., description="Owner tenant ID")
    
    # Configuration
    schema_id: Optional[str] = None
    extractor_id: Optional[str] = None
    classifier_id: Optional[str] = None
    splitter_id: Optional[str] = None
    
    # Results
    classification_result: Optional[Dict[str, Any]] = None
    split_chunks: Optional[List[Dict[str, Any]]] = None
    extracted_data: Optional[Dict[str, Any]] = None
    confidence_score: Optional[int] = None
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None
    
    # Errors
    error_message: Optional[str] = None
    
    created_at: datetime = Field(..., description="Run creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    metadata: Optional[Dict[str, Any]] = None


class ParseResult(BaseModel):
    """Complete result of a parse operation."""
    
    run_id: str = Field(..., description="Parser run identifier")
    file_id: str = Field(..., description="File parsed")
    status: Literal["completed", "failed"] = Field(..., description="Final status")
    
    # Results
    classification: Optional[Dict[str, Any]] = Field(None, description="Classification result")
    chunks: Optional[List[Dict[str, Any]]] = Field(None, description="Split chunks")
    extracted: Optional[Dict[str, Any]] = Field(None, description="Extracted data")
    confidence: Optional[float] = Field(None, description="Overall confidence (0.0-1.0)")
    
    # Timing
    processing_time_ms: int = Field(..., description="Processing duration")
    completed_at: datetime = Field(..., description="Completion timestamp")
    
    # Errors
    error: Optional[str] = Field(None, description="Error message if failed")


# Rebuild new models
FileUpload.model_rebuild()
ParserRunRequest.model_rebuild()
ParserRunStatus.model_rebuild()
ParseResult.model_rebuild()


# ======================
# PHASE 7: Processors, Workflows, Evaluation Sets
# ======================

class ProcessorConfig(BaseModel):
    """Processor configuration response."""
    
    processor_id: str = Field(..., description="Unique processor identifier")
    name: str = Field(..., description="Processor name")
    description: str = Field("", description="Processor description")
    processor_type: str = Field(..., description="Type of processor")
    implementation: Dict[str, Any] = Field(..., description="Implementation details")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="Input schema")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="Output schema")
    enabled: bool = Field(True, description="Whether processor is enabled")
    version: int = Field(1, description="Processor version")
    tenant_id: str = Field(..., description="Owner tenant ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class CreateProcessorRequest(BaseModel):
    """Request to create a processor."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Processor name")
    processor_type: str = Field(..., description="Type: extractor, transformer, validator, custom")
    implementation: Dict[str, Any] = Field(..., description="Implementation details")
    description: Optional[str] = Field(None, max_length=500, description="Description")
    input_schema: Optional[Dict[str, Any]] = Field(None, description="Expected input format")
    output_schema: Optional[Dict[str, Any]] = Field(None, description="Expected output format")
    enabled: bool = Field(True, description="Whether processor is enabled")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class UpdateProcessorRequest(BaseModel):
    """Request to update a processor."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    processor_type: Optional[str] = None
    implementation: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class ProcessorListResponse(BaseModel):
    """Response for processor list."""
    
    items: List[ProcessorConfig] = Field(..., description="List of processors")
    meta: Dict[str, Any] = Field(..., description="Pagination metadata")


class WorkflowConfig(BaseModel):
    """Workflow configuration response."""
    
    workflow_id: str = Field(..., description="Unique workflow identifier")
    name: str = Field(..., description="Workflow name")
    description: str = Field("", description="Workflow description")
    steps: List[Dict[str, Any]] = Field(..., description="Workflow steps")
    enabled: bool = Field(True, description="Whether workflow is enabled")
    version: int = Field(1, description="Workflow version")
    tenant_id: str = Field(..., description="Owner tenant ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class CreateWorkflowRequest(BaseModel):
    """Request to create a workflow."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Workflow name")
    steps: List[Dict[str, Any]] = Field(..., description="Workflow steps with processor references")
    description: Optional[str] = Field(None, max_length=500, description="Description")
    enabled: bool = Field(True, description="Whether workflow is enabled")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class UpdateWorkflowRequest(BaseModel):
    """Request to update a workflow."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    steps: Optional[List[Dict[str, Any]]] = None
    enabled: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class WorkflowListResponse(BaseModel):
    """Response for workflow list."""
    
    items: List[WorkflowConfig] = Field(..., description="List of workflows")
    meta: Dict[str, Any] = Field(..., description="Pagination metadata")


class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow."""
    
    input_data: Dict[str, Any] = Field(..., description="Input data for workflow")


class WorkflowExecutionResult(BaseModel):
    """Result of workflow execution."""
    
    workflow_id: str = Field(..., description="Workflow identifier")
    workflow_name: str = Field(..., description="Workflow name")
    input: Dict[str, Any] = Field(..., description="Input data")
    output: Dict[str, Any] = Field(..., description="Output data")
    steps: List[Dict[str, Any]] = Field(..., description="Step execution details")
    status: str = Field(..., description="Execution status")


class EvaluationSetConfig(BaseModel):
    """Evaluation set configuration response."""
    
    evaluation_set_id: str = Field(..., description="Unique evaluation set identifier")
    name: str = Field(..., description="Evaluation set name")
    description: str = Field("", description="Evaluation set description")
    test_cases: List[Dict[str, Any]] = Field(..., description="Test cases")
    target_type: str = Field(..., description="Target type: processor, workflow, extractor, schema")
    target_id: Optional[str] = Field(None, description="Specific target ID")
    tenant_id: str = Field(..., description="Owner tenant ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Results and metrics")


class CreateEvaluationSetRequest(BaseModel):
    """Request to create an evaluation set."""
    
    name: str = Field(..., min_length=1, max_length=100, description="Evaluation set name")
    test_cases: List[Dict[str, Any]] = Field(..., description="Test cases with input/expected output")
    target_type: str = Field(..., description="processor, workflow, extractor, or schema")
    description: Optional[str] = Field(None, max_length=500, description="Description")
    target_id: Optional[str] = Field(None, description="Specific target ID to evaluate")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class UpdateEvaluationSetRequest(BaseModel):
    """Request to update an evaluation set."""
    
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    test_cases: Optional[List[Dict[str, Any]]] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EvaluationSetListResponse(BaseModel):
    """Response for evaluation set list."""
    
    items: List[EvaluationSetConfig] = Field(..., description="List of evaluation sets")
    meta: Dict[str, Any] = Field(..., description="Pagination metadata")


class EvaluationResult(BaseModel):
    """Result of evaluation run."""
    
    evaluation_set_id: str = Field(..., description="Evaluation set identifier")
    evaluation_set_name: str = Field(..., description="Evaluation set name")
    target_type: str = Field(..., description="Target type")
    target_id: Optional[str] = Field(None, description="Target ID")
    total_tests: int = Field(..., description="Total number of tests")
    passed: int = Field(..., description="Number of passed tests")
    failed: int = Field(..., description="Number of failed tests")
    pass_rate: float = Field(..., description="Pass rate (0.0 to 1.0)")
    results: List[Dict[str, Any]] = Field(..., description="Individual test results")


# Rebuild PHASE 7 models
ProcessorConfig.model_rebuild()
CreateProcessorRequest.model_rebuild()
UpdateProcessorRequest.model_rebuild()
ProcessorListResponse.model_rebuild()
WorkflowConfig.model_rebuild()
CreateWorkflowRequest.model_rebuild()
UpdateWorkflowRequest.model_rebuild()
WorkflowListResponse.model_rebuild()
ExecuteWorkflowRequest.model_rebuild()
WorkflowExecutionResult.model_rebuild()
EvaluationSetConfig.model_rebuild()
CreateEvaluationSetRequest.model_rebuild()
UpdateEvaluationSetRequest.model_rebuild()
EvaluationSetListResponse.model_rebuild()
EvaluationResult.model_rebuild()
