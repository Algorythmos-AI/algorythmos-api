"""Core configuration constants and utilities for the API."""

# API Configuration
API_PREFIX = "/api"  # Root path configured in FastAPI app

# Tenant Context Key
TENANT_KEY = "tenant"  # Key used in tenant_ctx dict from require_key dependency

# Database Configuration
# Primary keys use 'id' column for all models
# Foreign keys use explicit naming like 'schema_id', 'file_id', etc.

# Pagination Defaults
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
DEFAULT_OFFSET = 0

# Soft Delete
# All mutable resources should have 'is_deleted' boolean column
# Default filter: WHERE is_deleted = False OR is_deleted IS NULL

# Error Response Shape
# Standard: { "error": { "type": "...", "message": "...", "details": {...}? } }

# API Versioning Headers
API_VERSION_HEADER = "x-api-version"
EXTEND_API_VERSION_HEADER = "x-extend-api-version"
DEFAULT_API_VERSION = "2024-10-19"  # Current date as default version

# Security Headers
API_KEY_HEADER = "X-API-Key"
TENANT_ID_HEADER = "X-Tenant-ID"
AUTHORIZATION_HEADER = "Authorization"
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

# Confidence Thresholds
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 1.0
DEFAULT_CONFIDENCE = 0.5

# Citation Types
CITATION_TYPES = ["regex", "llm", "template", "manual", "rule_based", "ml"]

# Extractor Types
EXTRACTOR_TYPES = ["regex", "llm", "template", "ml", "rule_based"]

# Classifier Types
CLASSIFIER_TYPES = ["keyword", "ml", "llm", "rule_based"]

# Splitter Types
SPLITTER_TYPES = ["page", "section", "pattern", "size", "heading"]

# File Types
SUPPORTED_FILE_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # DOCX
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # XLSX
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # PPTX
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/tiff",
]

# Run Statuses
RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_SUCCEEDED = "succeeded"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"

RUN_STATUSES = [
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCEEDED,
    RUN_STATUS_FAILED,
    RUN_STATUS_CANCELLED,
]

# Webhook Event Types
WEBHOOK_EVENTS = [
    "processor_run.created",
    "processor_run.completed",
    "processor_run.failed",
    "workflow_run.created",
    "workflow_run.completed",
    "workflow_run.failed",
    "file.uploaded",
    "file.parsed",
]


def get_api_version(headers: dict) -> str:
    """Extract API version from request headers."""
    return (
        headers.get(API_VERSION_HEADER) or
        headers.get(EXTEND_API_VERSION_HEADER) or
        DEFAULT_API_VERSION
    )


def build_error_response(
    error_type: str,
    message: str,
    details: dict | None = None
) -> dict:
    """Build standardized error response."""
    error = {
        "type": error_type,
        "message": message,
    }
    if details:
        error["details"] = details
    return {"error": error}


def build_pagination_meta(
    limit: int,
    offset: int,
    total: int
) -> dict:
    """Build standardized pagination metadata."""
    has_more = (offset + limit) < total
    next_offset = offset + limit if has_more else None
    
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        "next_offset": next_offset,
        "has_more": has_more,
    }
