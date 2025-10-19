"""Database models for generic document processing."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.models import Base


class ExtractionSchemaDB(Base):
    """Database model for extraction schemas."""
    
    __tablename__ = "extraction_schemas"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False)
    fields = Column(JSON, nullable=False)  # List of FieldDefinition dicts
    version = Column(Integer, nullable=False, default=1)
    schema_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata' to avoid SQLAlchemy reserved word
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<ExtractionSchema(id={self.id}, name={self.name})>"


class ExtractorDB(Base):
    """Database model for extractors."""
    
    __tablename__ = "extractors"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # regex, llm, template, ml, rule_based
    schema_id = Column(String, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    rules = Column(JSON, nullable=False)  # Type-specific extraction rules
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Extractor(id={self.id}, name={self.name}, type={self.type})>"


class ClassifierDB(Base):
    """Database model for classifiers."""
    
    __tablename__ = "classifiers"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # keyword, ml, llm, rule_based
    enabled = Column(Boolean, nullable=False, default=True)
    categories = Column(JSON, nullable=False)  # List of possible categories
    rules = Column(JSON, nullable=False)  # Type-specific classification rules
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Classifier(id={self.id}, name={self.name}, type={self.type})>"


class SplitterDB(Base):
    """Database model for splitters."""
    
    __tablename__ = "splitters"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)  # page, section, pattern, size
    enabled = Column(Boolean, nullable=False, default=True)
    rules = Column(JSON, nullable=False)  # Type-specific splitting rules
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Splitter(id={self.id}, name={self.name}, type={self.type})>"


class DocumentChunkDB(Base):
    """Database model for document chunks."""
    
    __tablename__ = "document_chunks"
    
    id = Column(String, primary_key=True)
    parent_document_id = Column(String, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_range_start = Column(Integer, nullable=True)
    page_range_end = Column(Integer, nullable=True)
    content_type = Column(String(100), nullable=False, default="application/pdf")
    content_size = Column(Integer, nullable=False)
    storage_path = Column(String, nullable=True)  # If content stored externally
    chunk_metadata = Column(JSON, nullable=True)  # Renamed from 'metadata'
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, parent={self.parent_document_id}, index={self.chunk_index})>"


class ExtractionResultDB(Base):
    """Database model for extraction results."""
    
    __tablename__ = "extraction_results"
    
    id = Column(String, primary_key=True)
    document_id = Column(String, nullable=False, index=True)
    schema_id = Column(String, nullable=False, index=True)
    extractor_id = Column(String, nullable=False)
    tenant_id = Column(String, nullable=False, index=True)
    fields = Column(JSON, nullable=False)  # List of ExtractedField dicts
    overall_confidence = Column(Integer, nullable=False)  # Stored as int (0-100)
    warnings = Column(JSON, nullable=True)  # List of warning strings
    processing_time_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    def __repr__(self) -> str:
        return f"<ExtractionResult(id={self.id}, document_id={self.document_id})>"


class FileDB(Base):
    """Database model for uploaded files."""
    
    __tablename__ = "files"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_path = Column(String, nullable=False)  # Path to file in storage
    checksum = Column(String(64), nullable=False)  # SHA-256 checksum
    file_metadata = Column(JSON, nullable=True)  # Additional metadata
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<File(id={self.id}, filename={self.filename})>"


class ParserRunDB(Base):
    """Database model for parser execution runs."""
    
    __tablename__ = "parser_runs"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    file_id = Column(String, nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)  # pending, running, completed, failed
    schema_id = Column(String, nullable=True)  # Optional: which schema to use
    extractor_id = Column(String, nullable=True)  # Optional: which extractor to use
    classifier_id = Column(String, nullable=True)  # Optional: classifier used
    splitter_id = Column(String, nullable=True)  # Optional: splitter used
    
    # Results
    classification_result = Column(JSON, nullable=True)  # Classification output
    split_chunks = Column(JSON, nullable=True)  # List of chunk metadata
    extracted_data = Column(JSON, nullable=True)  # Extracted fields
    confidence_score = Column(Integer, nullable=True)  # Overall confidence (0-100)
    
    # Execution metadata
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    run_metadata = Column(JSON, nullable=True)  # Additional run information
    
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<ParserRun(id={self.id}, file_id={self.file_id}, status={self.status})>"


class WebhookDB(Base):
    """Database model for webhook subscriptions."""
    
    __tablename__ = "webhooks"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    events = Column(JSON, nullable=False)  # List of event types to subscribe to
    enabled = Column(Boolean, nullable=False, default=True)
    secret = Column(String(100), nullable=True)  # Secret for signature verification
    
    # Delivery settings
    max_retries = Column(Integer, nullable=False, default=3)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    
    # Statistics
    last_triggered_at = Column(DateTime, nullable=True)
    total_deliveries = Column(Integer, nullable=False, default=0)
    successful_deliveries = Column(Integer, nullable=False, default=0)
    failed_deliveries = Column(Integer, nullable=False, default=0)
    
    # Metadata
    webhook_metadata = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Webhook(id={self.id}, name={self.name}, url={self.url})>"


class WebhookDeliveryDB(Base):
    """Database model for webhook delivery attempts."""
    
    __tablename__ = "webhook_deliveries"
    
    id = Column(String, primary_key=True)
    webhook_id = Column(String, nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    
    # Delivery status
    status = Column(String(20), nullable=False, index=True)  # pending, success, failed, retrying
    attempt_count = Column(Integer, nullable=False, default=0)
    
    # Response details
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timing
    scheduled_at = Column(DateTime, nullable=False, default=func.now())
    attempted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    next_retry_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<WebhookDelivery(id={self.id}, webhook_id={self.webhook_id}, status={self.status})>"


class ProcessorDB(Base):
    """Database model for processors (custom processing plugins)."""
    
    __tablename__ = "processors"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    processor_type = Column(String(50), nullable=False)  # 'extractor', 'transformer', 'validator', 'custom'
    implementation = Column(JSON, nullable=False)  # Contains code, config, or reference
    input_schema = Column(JSON, nullable=True)  # Expected input format
    output_schema = Column(JSON, nullable=True)  # Expected output format
    enabled = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    processor_metadata = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Processor(id={self.id}, name={self.name}, type={self.processor_type})>"


class ProcessorVersionDB(Base):
    """Database model for processor versions (Sprint 4 - P3.1-P3.2)."""
    
    __tablename__ = "processor_versions"
    
    id = Column(String, primary_key=True)
    processor_id = Column(String, nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    version_number = Column(Integer, nullable=False)  # Sequential version number
    
    # Version content (snapshot of processor at version creation)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    processor_type = Column(String(50), nullable=False)
    implementation = Column(JSON, nullable=False)
    input_schema = Column(JSON, nullable=True)
    output_schema = Column(JSON, nullable=True)
    
    # Version lifecycle
    status = Column(String(20), nullable=False, default='draft', index=True)  # draft, published, deprecated
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    published_at = Column(DateTime, nullable=True)
    deprecated_at = Column(DateTime, nullable=True)
    
    # Change tracking
    change_notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    
    # Metadata
    version_metadata = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<ProcessorVersion(id={self.id}, processor_id={self.processor_id}, version={self.version_number}, status={self.status})>"


class WorkflowDB(Base):
    """Database model for workflows (chains of processors)."""
    
    __tablename__ = "workflows"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    steps = Column(JSON, nullable=False)  # List of workflow steps with processor references
    enabled = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    workflow_metadata = Column(JSON, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Workflow(id={self.id}, name={self.name})>"


class EvaluationSetDB(Base):
    """Database model for evaluation sets (test datasets)."""
    
    __tablename__ = "evaluation_sets"
    
    id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    test_cases = Column(JSON, nullable=False)  # List of test cases with input/expected output
    target_type = Column(String(50), nullable=False)  # 'processor', 'workflow', 'extractor', 'schema'
    target_id = Column(String, nullable=True)  # ID of target processor/workflow/etc.
    evaluation_metadata = Column(JSON, nullable=True)  # Results, metrics, etc.
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<EvaluationSet(id={self.id}, name={self.name}, target={self.target_type})>"
