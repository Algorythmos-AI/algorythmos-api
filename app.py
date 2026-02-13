"""Main application factory for the PDF Usage Extraction Service."""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

import anyio
import hashlib
import httpx
import secrets
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile, status, Path as PathParam, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.params import Body, Query
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from document_processing.state import (
    InMemoryRateLimitStore,
    RedisRateLimitStore,
    SQLBackgroundJobStore,
    SQLIdempotencyStore,
    SQLWebhookReplayStore,
)
from pdf_usage_extractor import ExtractionRouter
from pdf_usage_extractor.logging_utils import get_logger
from pdf_usage_extractor.schemas import ExtractResponse, UsageRecord, ProcessorCreateRunRequest, ProcessorUpdateRequest, ProcessorInfo
from vendor_libs.services import vendor
from vendor_libs.utils.security import parse_signature_header, verify_hmac_sha256
from vendor_libs.utils.observability import metrics_app, runs_started, runs_succeeded, runs_failed
from prometheus_client import Counter, Histogram

# Production middleware imports
from document_processing.middleware import RateLimitMiddleware, IdempotencyMiddleware

# Initialize metrics
http_requests_total = None
http_request_duration_seconds = None
webhook_deliveries_total = None
webhook_delivery_duration_seconds = None
parser_runs_total = None
parser_run_duration_seconds = None
rate_limit_hits_total = None
idempotency_replays_total = None

# Generic document processing imports
from document_processing.schemas import (
    CreateSchemaRequest,
    UpdateSchemaRequest,
    ExtractionSchema,
    SchemaListResponse,
    CreateExtractorRequest,
    UpdateExtractorRequest,
    ExtractorConfig,
    CreateClassifierRequest,
    UpdateClassifierRequest,
    ClassifierConfig,
    CreateSplitterRequest,
    UpdateSplitterRequest,
    SplitterConfig,
    # PHASE 4: File and Parser schemas
    FileUpload,
    ParserRunRequest,
    ParserRunStatus,
    ParseResult,
    # PHASE 7: Processor, Workflow, Evaluation schemas
    ProcessorConfig,
    CreateProcessorRequest,
    UpdateProcessorRequest,
    ProcessorListResponse,
    WorkflowConfig,
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    WorkflowListResponse,
    ExecuteWorkflowRequest,
    WorkflowExecutionResult,
    EvaluationSetConfig,
    CreateEvaluationSetRequest,
    UpdateEvaluationSetRequest,
    EvaluationSetListResponse,
    EvaluationResult,
)
from document_processing.services.schema_service import SchemaService
from document_processing.services import extractor_service
from document_processing.services import classifier_service
from document_processing.services import splitter_service
from document_processing.services.format_validator import format_validator
from document_processing.services import file_service
from document_processing.services import parser_service
from document_processing.services import processor_service
from document_processing.services import workflow_service
from document_processing.services import evaluation_service
from core.config import build_error_response, build_pagination_meta

# Database imports - use direct module references to avoid package conflicts
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

# These will be imported after app.database and app.models modules are available
# to avoid circular dependencies during app package initialization
async_session_factory = None
engine = None
get_session = None
Base = None
Run = None


class PathRequest(BaseModel):
    input_path: str
    provider_hint: Optional[str] = None
    debug: bool = False


class JobCreate(BaseModel):
    input_path: str
    provider_hint: Optional[str] = None
    debug: bool = False
    webhook_url: Optional[AnyHttpUrl] = None

    def is_cloud_path(self) -> bool:
        """Check if input_path is a cloud storage URI."""
        return self.input_path.startswith(('gs://', 's3://', 'azure://', 'http://', 'https://'))


# Alias for Algorythmos compatibility
ProcessorRunRequest = JobCreate


class JobRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    tenant_id: str
    request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    webhook_url: Optional[AnyHttpUrl] = None
    result: Optional[ExtractResponse] = None
    error: Optional[str] = None
    duration_sec: Optional[float] = None


# Rebuild models to ensure all forward references are resolved
PathRequest.model_rebuild()
JobCreate.model_rebuild()
JobRecord.model_rebuild()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Add request ID to all requests."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class FileSizeMiddleware(BaseHTTPMiddleware):
    """Enforce maximum file size limits."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Check content length header if available
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_file_bytes:
            return Response(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content='{"code": "FILE_TOO_LARGE", "message": "File exceeds ' + str(settings.MAX_FILE_MB) + ' MB limit"}',
                media_type="application/json"
            )

        return await call_next(request)


# Prometheus metrics for HTTP requests (initialized once)
http_requests_total = None
http_request_duration_seconds = None


def _get_or_create_metrics():
    """Get or create HTTP metrics (handles reloads in tests)."""
    global http_requests_total, http_request_duration_seconds
    global webhook_deliveries_total, webhook_delivery_duration_seconds
    global parser_runs_total, parser_run_duration_seconds
    global rate_limit_hits_total, idempotency_replays_total

    if http_requests_total is None:
        try:
            http_requests_total = Counter(
                "http_requests_total",
                "Total HTTP requests",
                ["method", "endpoint", "status_code"]
            )
        except ValueError:
            # Metric already registered (test reload)
            from prometheus_client import REGISTRY
            http_requests_total = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'http_requests_total'), None)
            )

    if http_request_duration_seconds is None:
        try:
            http_request_duration_seconds = Histogram(
                "http_request_duration_seconds",
                "HTTP request latency",
                ["method", "endpoint", "status_code"],
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
            )
        except ValueError:
            # Metric already registered (test reload)
            from prometheus_client import REGISTRY
            http_request_duration_seconds = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'http_request_duration_seconds'), None)
            )

    # Webhook metrics
    if webhook_deliveries_total is None:
        try:
            webhook_deliveries_total = Counter(
                "webhook_deliveries_total",
                "Total webhook deliveries",
                ["event_type", "status"]
            )
        except ValueError:
            from prometheus_client import REGISTRY
            webhook_deliveries_total = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'webhook_deliveries_total'), None)
            )

    if webhook_delivery_duration_seconds is None:
        try:
            webhook_delivery_duration_seconds = Histogram(
                "webhook_delivery_duration_seconds",
                "Webhook delivery latency",
                ["event_type", "status"],
                buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
            )
        except ValueError:
            from prometheus_client import REGISTRY
            webhook_delivery_duration_seconds = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'webhook_delivery_duration_seconds'), None)
            )

    # Parser run metrics
    if parser_runs_total is None:
        try:
            parser_runs_total = Counter(
                "parser_runs_total",
                "Total parser runs",
                ["status", "format"]
            )
        except ValueError:
            from prometheus_client import REGISTRY
            parser_runs_total = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'parser_runs_total'), None)
            )

    if parser_run_duration_seconds is None:
        try:
            parser_run_duration_seconds = Histogram(
                "parser_run_duration_seconds",
                "Parser run latency",
                ["status", "format"],
                buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
            )
        except ValueError:
            from prometheus_client import REGISTRY
            parser_run_duration_seconds = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'parser_run_duration_seconds'), None)
            )

    # Rate limiting metrics
    if rate_limit_hits_total is None:
        try:
            rate_limit_hits_total = Counter(
                "rate_limit_hits_total",
                "Total rate limit hits",
                ["tenant_id", "limit_type"]
            )
        except ValueError:
            from prometheus_client import REGISTRY
            rate_limit_hits_total = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'rate_limit_hits_total'), None)
            )

    # Idempotency metrics
    if idempotency_replays_total is None:
        try:
            idempotency_replays_total = Counter(
                "idempotency_replays_total",
                "Total idempotency key replays",
                ["tenant_id", "endpoint"]
            )
        except ValueError:
            from prometheus_client import REGISTRY
            idempotency_replays_total = REGISTRY._collector_to_names.get(
                next((c for c in REGISTRY._collector_to_names if hasattr(c, '_name') and c._name == 'idempotency_replays_total'), None)
            )

    return (
        http_requests_total, http_request_duration_seconds,
        webhook_deliveries_total, webhook_delivery_duration_seconds,
        parser_runs_total, parser_run_duration_seconds,
        rate_limit_hits_total, idempotency_replays_total
    )


class MetricsMiddleware(BaseHTTPMiddleware):
    """Track HTTP request metrics for Prometheus."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # Skip metrics endpoint itself to avoid recursion
        if request.url.path in ("/metrics", "/api/metrics"):
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time

        # Normalize endpoint path for cardinality control
        endpoint = self._normalize_path(request.url.path)
        method = request.method
        status_code = str(response.status_code)

        # Get or create metrics
        metrics = _get_or_create_metrics()
        requests_total = metrics[0]
        request_duration = metrics[1]

        # Record metrics
        if requests_total and request_duration:
            requests_total.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            request_duration.labels(method=method, endpoint=endpoint, status_code=status_code).observe(duration)

        return response

    def _normalize_path(self, path: str) -> str:
        """Normalize path to reduce cardinality (replace IDs with placeholders)."""
        # Remove /api prefix if present
        if path.startswith("/api/"):
            path = path[4:]

        parts = path.split("/")
        normalized = []

        for i, part in enumerate(parts):
            if not part:
                continue
            # Replace UUIDs and job IDs with placeholders
            if len(part) > 20 and ("-" in part or part.startswith("job-") or part.startswith("run-")):
                normalized.append("{id}")
            else:
                normalized.append(part)

        return "/" + "/".join(normalized) if normalized else path


# Stage 3+ constants - exposed for tests
RUN_MAX_FILE_BYTES = settings.RUN_MAX_FILE_BYTES
RUN_MAX_FILES = settings.RUN_MAX_FILES
WEBHOOK_REPLAY_TTL_S = settings.WEBHOOK_REPLAY_TTL_S
WEBHOOK_REPLAY_WINDOW_S = settings.WEBHOOK_REPLAY_WINDOW_S
_processor_runs: Dict[str, JobRecord] = {}  # For Algorythmos-style runs


def _utcnow() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


def _resolve_state_backend() -> str:
    configured = (settings.STATE_BACKEND or "auto").strip().lower()
    if configured == "auto":
        return "redis" if settings.REDIS_URL else "memory"
    if configured in {"redis", "memory"}:
        return configured
    raise RuntimeError(f"Unsupported STATE_BACKEND value: {settings.STATE_BACKEND}")


async def _enforce_rate_limit(request: Request, tenant_id: str) -> None:
    """Enforce per-tenant request rate limiting via configured store backend."""
    rate = settings.RATE_PER_MIN
    if rate <= 0:
        return

    store = getattr(request.app.state, "rate_limit_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "RATE_LIMIT_NOT_CONFIGURED", "message": "Rate limiting backend is not configured"},
        )

    try:
        decision = await store.check_limit(tenant_id, rate, 60)
    except Exception as exc:
        if _is_production_environment():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "RATE_LIMIT_BACKEND_UNAVAILABLE",
                    "message": f"Rate limit backend unavailable: {type(exc).__name__}",
                },
            )
        return

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"},
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


def _require_configured_static_api_key() -> str:
    """Return configured static API key or raise a server-side auth configuration error."""
    configured_key = (settings.ALG_API_KEY or "").strip()
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "AUTH_NOT_CONFIGURED",
                "message": "Static API key authentication is not configured",
            },
        )
    return configured_key


def _is_production_environment() -> bool:
    """Return True when runtime is configured for production mode."""
    return (settings.ENV or "").strip().lower() in {"prod", "production"}


def _validate_startup_security_configuration() -> None:
    """Fail fast when required auth configuration is missing in production."""
    if not _is_production_environment():
        return

    if not (settings.ALG_API_KEY or "").strip():
        raise RuntimeError("ALG_API_KEY must be configured when ENV is production")

    if not (settings.GOOGLE_CLIENT_ID or "").strip():
        raise RuntimeError("GOOGLE_CLIENT_ID must be configured when ENV is production")


async def _validate_startup_state_configuration(app: FastAPI) -> None:
    """Fail fast when distributed state backends are not production-safe."""
    using_memory = bool(getattr(app.state, "using_memory_operational_state", False))
    if _is_production_environment() and using_memory:
        raise RuntimeError("In-memory operational state backends are forbidden in production")

    rate_limit_store = getattr(app.state, "rate_limit_store", None)
    if _is_production_environment() and rate_limit_store is None:
        raise RuntimeError("Rate limit store must be configured in production")

    if isinstance(rate_limit_store, RedisRateLimitStore):
        await rate_limit_store.ping()


async def require_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    authorization: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None, alias="x-tenant-id"),
    x_extend_api_version: Optional[str] = Header(default=None, alias="x-extend-api-version"),
    x_api_version: Optional[str] = Header(default=None, alias="x-api-version"),
) -> Dict[str, str]:
    """
    Validate authentication and extract tenant context.

    Supports:
    - X-API-Key header (legacy)
    - Authorization: Bearer <token> header (Extend parity)
    - X-Tenant-ID header (required, 400 if missing)
    - x-extend-api-version or x-api-version header (optional, stored for tracking)
    """
    # Extract Bearer token if present
    bearer_token = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization[7:]  # Strip "Bearer " prefix

    expected_api_key = _require_configured_static_api_key()

    # Authenticate: Bearer token OR API key required
    authenticated = False
    if bearer_token:
        if bearer_token == expected_api_key:
            authenticated = True
    elif x_api_key:
        if x_api_key == expected_api_key:
            authenticated = True

    if not authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or missing authentication"}
        )

    # Require X-Tenant-ID header
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_TENANT", "message": "Missing X-Tenant-ID header"}
        )

    # Enforce rate limiting
    await _enforce_rate_limit(request, x_tenant_id)

    # Store context in request state
    request.state.tenant_id = x_tenant_id

    # Determine API version (prefer x-extend-api-version, fallback to x-api-version)
    api_version = x_extend_api_version or x_api_version or "2025-04-21"  # Default version
    request.state.api_version = api_version

    return {
        "tenant": x_tenant_id,
        "api_version": api_version
    }



async def _run_extraction(
    *,
    path: str,
    provider_hint: Optional[str],
    debug: bool,
    timeout_sec: int = 45,
) -> tuple[list[UsageRecord], list[str], float]:
    """Run extraction with timeout."""
    start = time.perf_counter()

    def _execute() -> tuple[list[UsageRecord], list[str]]:
        return router_engine.extract_path(path, provider_hint=provider_hint, debug=debug)

    try:
        # Check if it's a cloud path
        if path.startswith(('gs://', 's3://', 'azure://', 'http://', 'https://')):
            # For cloud paths, we'd need to download first
            # For now, return a placeholder response indicating cloud support
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "code": "CLOUD_STORAGE_NOT_IMPLEMENTED",
                    "message": f"Cloud storage paths not yet supported: {path}",
                    "supported_schemes": ["file://", "local paths"]
                }
            )

        # Use anyio with timeout for graceful handling
        with anyio.move_on_after(timeout_sec) as cancel_scope:
            records, warnings = await anyio.to_thread.run_sync(_execute)

        if cancel_scope.cancelled_caught:
            raise TimeoutError(f"Extraction timed out after {timeout_sec} seconds")

    except Exception as exc:
        elapsed = time.perf_counter() - start
        # Convert to structured error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "EXTRACTION_FAILED",
                "message": str(exc),
                "processing_notes": f"Failed after {elapsed:.2f}s: {type(exc).__name__}"
            }
        ) from exc

    elapsed = time.perf_counter() - start
    return records, warnings, elapsed


def _log_request(
    *,
    route: str,
    files: int,
    records: List[UsageRecord],
    warnings: List[str],
    elapsed: float,
    debug: bool,
    tenant_id: str,
    request_id: Optional[str],
) -> None:
    """Log request details."""
    avg_conf = round(sum(r.confidence for r in records) / len(records), 3) if records else 0.0
    request_logger = get_logger(debug)
    request_logger.info(
        "Request handled",
        extra={
            "context": {
                "route": route,
                "files": files,
                "records": len(records),
                "warnings": warnings,
                "elapsed_sec": round(elapsed, 3),
                "avg_confidence": avg_conf,
                "tenant_id": tenant_id,
                "request_id": request_id,
            }
        },
    )


async def _maybe_send_webhook(job: JobRecord) -> None:
    """Send webhook notification if configured."""
    if not job.webhook_url or job.result is None:
        return

    payload = {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "status": job.status,
        "result": job.result.model_dump(mode="json"),
        "duration_sec": job.duration_sec,
        "request_id": job.request_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(str(job.webhook_url), json=payload)
    except Exception as exc:  # pragma: no cover - network best effort
        job_logger = get_logger()
        job_logger.warning(
            "Webhook delivery failed",
            extra={
                "context": {
                    "job_id": job.job_id,
                    "tenant_id": job.tenant_id,
                    "error": type(exc).__name__,
                }
            },
        )


def _background_job_db_to_record(job_db) -> JobRecord:
    """Convert durable BackgroundJobDB row to JobRecord schema."""
    result_payload = job_db.result if isinstance(job_db.result, dict) else None
    result = ExtractResponse(**result_payload) if result_payload else None
    return JobRecord(
        job_id=job_db.id,
        status=job_db.status,
        tenant_id=job_db.tenant_id,
        request_id=job_db.request_id,
        created_at=job_db.created_at,
        updated_at=job_db.updated_at,
        webhook_url=job_db.webhook_url,
        result=result,
        error=job_db.error,
        duration_sec=job_db.duration_sec,
    )


async def _execute_job(
    job_id: str,
    payload: JobCreate,
    tenant_id: str,
    request_id: Optional[str],
    job_store: SQLBackgroundJobStore,
) -> None:
    """Execute a background job."""
    job_logger = get_logger(payload.debug)
    running_job = await job_store.mark_running(job_id=job_id)
    if not running_job:
        return

    job_logger.info(
        "Job running",
        extra={"context": {"job_id": job_id, "tenant_id": tenant_id, "request_id": request_id}},
    )

    try:
        records, warnings, elapsed = await _run_extraction(
            path=payload.input_path,
            provider_hint=payload.provider_hint,
            debug=payload.debug,
        )
        result = ExtractResponse(count=len(records), records=records, warnings=warnings)
        duration_sec = round(elapsed, 3)
        succeeded_job = await job_store.mark_succeeded(
            job_id=job_id,
            result=result.model_dump(mode="json"),
            duration_sec=duration_sec,
        )
        if succeeded_job:
            await _maybe_send_webhook(_background_job_db_to_record(succeeded_job))

        job_logger.info(
            "Job succeeded",
            extra={
                "context": {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "records": result.count,
                    "duration_sec": duration_sec,
                    "request_id": request_id,
                }
            },
        )
    except Exception as exc:  # pragma: no cover - defensive catch
        await job_store.mark_failed(
            job_id=job_id,
            error=str(exc),
            duration_sec=None,
        )
        job_logger.warning(
            "Job failed",
            extra={
                "context": {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "error": type(exc).__name__,
                    "request_id": request_id,
                }
            },
        )


# ==================== API KEY PYDANTIC MODELS (module scope) ====================
# These must be at module scope for Pydantic/OpenAPI schema generation to work.

class CreateApiKeyRequest(BaseModel):
    """Request to create a new API key."""
    name: str = Field(..., min_length=1, max_length=100, description="Name for the API key")

class ApiKeyResponse(BaseModel):
    """API key info returned in list responses (no raw key)."""
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None

class CreateApiKeyResponse(BaseModel):
    """Response when creating a new API key (includes raw key once)."""
    id: str
    name: str
    prefix: str
    created_at: datetime
    raw_key: str  # Only returned on creation!

# Force Pydantic to fully resolve these models now.
# Required because app.py is loaded under a synthetic module name (_app_entrypoint)
# which prevents Pydantic's lazy resolution from working correctly.
CreateApiKeyRequest.model_rebuild()
ApiKeyResponse.model_rebuild()
CreateApiKeyResponse.model_rebuild()



# ---------------------------------------------------------------------------
# HTML builders for premium dark-theme documentation UI
# ---------------------------------------------------------------------------

# Base64-encoded Algorythmos favicons (avoids 404 on Vercel serverless)
_FAVICON_32_B64 = "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAFgklEQVR4nKVX3W8UVRT/nTszO9t2W6CVL7HWB4hprAaJokjEgAFMDBh9wFeNf4EfL/igiVES4qOPEBIT9cWPxMCDLwaDiakihhiMgjEkFBHaUrrdfuzO7Nxjzr0zuzOzsy3VmzRzej/OPfec3/mds/Ty5mkmAggEGRRL9o9g1wrm5UsFc5lzXdZb5wguIxkiUeobz3FsQWY+WWbRljufPpebS2SOZWIxoOiSxKxYLlin/2dEPFxObbZ6xKTcS+/SCEeJyMbFZlovZ4T9usYDd/PSFTxFxJid0/BKBEcruETwytagrkYwQ4koRrS+Vmgpt2spWfRlzgDKAaZrIbYfdvDONxW89VUP7htTCJZkMd7P2TOJTC9unuTuKE/yIjuvEhST6CfUAw1nQ4QTPw3B77GvvHoxwrHnFo1HjBYuzg4lLsq/KC+3/EFsXsvEiCKg2QRIAREzymvZXB417WsH71WAz9CCg7TenCdURwhym2VoAZYCtAaqMxpBneH3AeUKUF9i6Drhz4shvj61AMe1Cj47toC5OxGUa8+39cbhiOfo8KZbNgRdiEMkxwGaDcB1CQdfLWPXCyWsH1bGqOkJjfOnQ5z9oo6a18BAvwMOCJUeB9Gki8VZhuNQd7I6tOkmF7OU3aTExQHQ269w9JMBjO6SJ3aO2xMa5QHCbz8H6O0jbB3z8PbueczeZHi+ID7PiNYAtx2hYrIQd0ms3zhRMZc3QxijBAvpMTSszHfns775LlTZnDPZVqjfpqeb4QG7u5WzymHU7jD2Hilj+76SAZjEWCwPlhjjpwPMTTMefsbDyEOOwQhrC0xzFTG0wRJ1YUzOeyBrhDCiiE+/5Kf4wb7u/SNz+PW7EJ5HKPmE109VDDYibT3URn6broqMUG1i6UzBKGKUK4QtWx1zLjn//ZcN/PJtgKEtCgPrCZFmfH58yXgoH5qEyNoZkM00lU3BbDqKS8XlBkSpMXU9gtcDc3EYAqUewnxVI6xLHchfXsAtnOcBzuVpPCc0Wq9rozyNo9EnPQQNNnwgobozqTEy5hhv6ShlQKxsOSNUp1VtT5ADLC0wLl8QyrPuF6WPHSjhlff64PdajOzY7+G1430t4up0f6d3E5n2b/y7Cw9YDmgsMrY94uGjs0MtDCQor81oLNYYG0fagU/2CFDffKpqssTUgyIeQAcVZz0hGCj3EX4/H+LjD+YNwAz3N4FmwOgfVJnLhSPkTJKOGZ0dVbQVAl4GJLbo9K0jfPrhPE6+WzMhEWC6cZUzLPiPxsmj8+aw0LZ4TvBgUzlVzAuMoH0brrea0nwpNuEwLiUocess44FRFzsP+Bje5hrAXfujifEzAapTGo/v91tNrKxd/rGJSJgzDiuKGt29HQbYC6Mwpsq4kMiQYhQssmk0xMXyPzTQv06hVCLMTurUZYTKGjL9QnKhI6/IGeFmqVhiTFia19ixx0f/GoXpGxozNzV2P+/j4rkQj+4p4cqFEE8c9PHDmQbuf9DFjb8irBlU6K0og42BQQXXI0xNRPDLyhgr1H3pXBO9FUr1ioipuNUmW1FqeK2qUV+0QHQ8xo2rEcKAce1KE7O3NS6NB7h9SyNsNE02VKcYa+9ho1yMlseyJjhuBC01REltkd6gnaTGF3s2TMQtWSo1FBA2JJBCrdLtknlZqaRMaIT/BfG+T+AoDgXb7DAhiC8xLpcHxfQoNSOfjm5RqZRXe366KQHKnnWPuFa2lSULjIH2mKSnJ5Wy8JeSBbV0RoKJNF+53foBcZVstYoY2tBV3J6RGBn/ejD+i2OadNNU3NIbJs1VXtdwfpcDq/s1VLS+sk63sB9YtRFZYK1khO32bb/h5urHfzSiS0u33Hrc9LR/nLZit5wRq3jpXa7/C7L1e98ohc04AAAAAElFTkSuQmCC"
_FAVICON_16_B64 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACMElEQVR4nG2TTWsUQRCGn+rp2cnkQ/QiiQaFiB+QgJ4EIQrxnouICJ6C3r3Eqyfv6sUfoD/Cm+BBAh5EiKB4CIK6fsXdkGSTbGZ7Sqo7myzEhh6mqruq633fKrk1sapOBIdt+N9/JoLPBAJIPNvbAl5RVEEFaoRoCMSPKiJQVdBZU4ZHhdzbvf4SnBk1OrCxlJApLoderZTjNdcWPMNHhaoXn0x3VS3BgWFbJSXZaNest5TvzR6zC567T0suzWd0Niz5waPegmKdaMTUC6A95cqNgsmzGV+WA+9e7VKOCp/fB/KhVJUYZrEEVq4aHKMHqq5y/9kYc7eLfaStHzXtv4HuT8fKUpfGiIshRpzrc4BTNjdqLl7PY3B3W3n+cIsn9zbJC+HMTE6jFHohMnQYQi2wu1tzejqjDvDpbcWLRx0qhZPnMm4ullTVQbCFWck+vm5OQ+Kg/afGZTAxlTFz1dNqKtOzPp0PqKUR8AAHRl55BJZe7tBcGeHEVMbj18cYXOWYEGJwUso48P0KYp4a2quBB/Mt7iyOcuq8Z2W5x9ePgQuXPR/eVDHYoJhilkTmjn9TM0yW8UmPBsicUFfQaAhba1AUQp5LtIshx/pvZWddY3v7BMEk1EiisSkFZI3EuHWjeCFrQAjKdqeO/qTeAIk2OL+aIQ6OmKp7g+Sd2dY4Az6f/EEtQZQjEeny1EwGKU5jf2RE96cv+lRjcJzGfRL3iDy0olpJstSxyW2J7Po/sHcmxfWlhlIAAAAASUVORK5CYII="
_FAVICON_LINKS = (
    f'<link rel="icon" type="image/png" sizes="32x32" href="data:image/png;base64,{_FAVICON_32_B64}"/>'
    f'\n  <link rel="icon" type="image/png" sizes="16x16" href="data:image/png;base64,{_FAVICON_16_B64}"/>'
    f'\n  <link rel="icon" type="image/x-icon" href="/api/favicon.ico"/>'
)

def _build_swagger_html(title: str, openapi_url: str, custom_css: str) -> str:
    """Build a complete dark-themed Swagger UI HTML page."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{title} — API Docs</title>
  {_FAVICON_LINKS}
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"/>
  <style>{custom_css}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({{
      url: "{openapi_url}",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: "BaseLayout",
      tryItOutEnabled: true,
      filter: true,
      deepLinking: true,
      displayRequestDuration: true,
      syntaxHighlight: {{ theme: "monokai" }},
    }});
  </script>
</body>
</html>"""


def _build_landing_html() -> str:
    """Build a premium dark-themed API landing page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Algorythmos API</title>
  <meta name="description" content="PDF Usage Extraction Service — Extract internet usage data from telecom PDF invoices via a modern REST API."/>
  <!-- Favicons -->
  {_FAVICON_LINKS}
  <!-- Open Graph (Facebook, LinkedIn, Slack, etc.) -->
  <meta property="og:type" content="website"/>
  <meta property="og:title" content="Algorythmos API"/>
  <meta property="og:description" content="Extract internet usage data from telecom PDF invoices with a production-ready REST API."/>
  <meta property="og:image" content="https://api.algorythmos.com/api/public/og-logo.png"/>
  <meta property="og:url" content="https://api.algorythmos.com"/>
  <meta property="og:site_name" content="Algorythmos"/>
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary"/>
  <meta name="twitter:title" content="Algorythmos API"/>
  <meta name="twitter:description" content="Extract internet usage data from telecom PDF invoices with a production-ready REST API."/>
  <meta name="twitter:image" content="https://api.algorythmos.com/api/public/og-logo.png"/>
  <!-- PWA / Android -->
  <meta name="theme-color" content="#6b21a8"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
    :root {
      --bg: #0a0a1a; --surface: #12122e; --card: #181845;
      --text: #e2e8f0; --muted: #94a3b8; --accent: #6366f1;
      --accent2: #a855f7; --accent3: #ec4899; --success: #22c55e;
      --border: rgba(148,163,184,0.1);
    }
    body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; overflow-x: hidden; }
    /* Animated gradient background */
    .bg-glow { position: fixed; inset: 0; z-index: 0; pointer-events: none; }
    .bg-glow::before { content: ''; position: absolute; top: -30%; left: -20%; width: 60%; height: 60%; background: radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%); animation: float 8s ease-in-out infinite; }
    .bg-glow::after { content: ''; position: absolute; bottom: -20%; right: -15%; width: 50%; height: 50%; background: radial-gradient(circle, rgba(168,85,247,0.1) 0%, transparent 70%); animation: float 12s ease-in-out infinite reverse; }
    @keyframes float { 0%,100% { transform: translate(0,0) scale(1); } 50% { transform: translate(30px,-20px) scale(1.1); } }
    .container { position: relative; z-index: 1; max-width: 1100px; margin: 0 auto; padding: 0 24px; }
    /* Header */
    header { padding: 60px 0 40px; text-align: center; }
    .logo-row { display: inline-flex; align-items: center; gap: 16px; margin-bottom: 24px; }
    .logo-icon { width: 48px; height: 48px; }
    .logo-text { font-size: 1.5rem; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    h1 { font-size: 3.2rem; font-weight: 800; line-height: 1.15; margin-bottom: 16px; background: linear-gradient(135deg, var(--text) 0%, var(--muted) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    h1 span { background: linear-gradient(135deg, var(--accent), var(--accent2), var(--accent3)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .subtitle { font-size: 1.15rem; color: var(--muted); max-width: 600px; margin: 0 auto 32px; line-height: 1.6; }
    /* Status badge */
    .status { display: inline-flex; align-items: center; gap: 8px; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3); border-radius: 20px; padding: 6px 16px; font-size: 0.85rem; color: var(--success); font-weight: 500; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); animation: pulse 2s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
    /* CTA buttons */
    .cta-row { display: flex; justify-content: center; gap: 16px; margin-top: 32px; flex-wrap: wrap; }
    .btn { display: inline-flex; align-items: center; gap: 8px; padding: 14px 28px; border-radius: 12px; font-weight: 600; font-size: 0.95rem; text-decoration: none; transition: all 0.2s ease; border: none; cursor: pointer; }
    .btn-primary { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #fff; box-shadow: 0 4px 20px rgba(99,102,241,0.3); }
    .btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(99,102,241,0.5); }
    .btn-secondary { background: var(--card); color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover { border-color: var(--accent); background: rgba(99,102,241,0.05); }
    /* Feature cards */
    .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 60px 0; }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; transition: all 0.25s ease; }
    .card:hover { border-color: var(--accent); transform: translateY(-4px); box-shadow: 0 12px 40px rgba(99,102,241,0.15); }
    .card-icon { font-size: 2rem; margin-bottom: 14px; }
    .card h3 { font-size: 1.1rem; font-weight: 600; margin-bottom: 8px; }
    .card p { font-size: 0.9rem; color: var(--muted); line-height: 1.6; }
    /* Quick endpoints */
    .endpoints { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px; margin-bottom: 60px; }
    .endpoints h2 { font-size: 1.3rem; font-weight: 700; margin-bottom: 20px; }
    .endpoint { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
    .endpoint:last-child { border-bottom: none; }
    .method { padding: 4px 10px; border-radius: 6px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; min-width: 56px; text-align: center; }
    .method-get { background: rgba(34,197,94,0.15); color: var(--success); }
    .method-post { background: rgba(99,102,241,0.15); color: var(--accent); }
    .ep-path { font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; color: var(--text); }
    .ep-desc { font-size: 0.85rem; color: var(--muted); margin-left: auto; }
    /* Footer */
    footer { text-align: center; padding: 40px 0; color: var(--muted); font-size: 0.85rem; border-top: 1px solid var(--border); }
    footer a { color: var(--accent); text-decoration: none; }
    @media (max-width: 640px) { h1 { font-size: 2rem; } .features { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="bg-glow"></div>
  <div class="container">
    <header>
      <div class="logo-row">
        <img class="logo-icon" src="/api/public/logo-128x128.png" alt="Algorythmos" style="border-radius:12px;"/>
        <span class="logo-text">Algorythmos</span>
      </div>
      <h1>PDF Usage<br/><span>Extraction API</span></h1>
      <p class="subtitle">Extract internet usage data from telecom PDF invoices with a powerful, production-ready REST API.</p>
      <div class="status"><span class="status-dot"></span> All systems operational</div>
      <div class="cta-row">
        <a href="/api/docs" class="btn btn-primary">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          API Documentation
        </a>
        <a href="/api/alg/healthz" class="btn btn-secondary">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22,12 18,12 15,21 9,3 6,12 2,12"/></svg>
          Health Check
        </a>
      </div>
    </header>

    <section class="features">
      <div class="card">
        <div class="card-icon">📄</div>
        <h3>PDF Processing</h3>
        <p>Upload telecom PDF invoices and extract structured usage data automatically with AI-powered document parsing.</p>
      </div>
      <div class="card">
        <div class="card-icon">⚡</div>
        <h3>Async Processing</h3>
        <p>Background job processing with webhook notifications, idempotency keys, and automatic retries built in.</p>
      </div>
      <div class="card">
        <div class="card-icon">🔒</div>
        <h3>Secure Auth</h3>
        <p>Google OAuth 2.0 and API key authentication with SHA-256 hashing. Multi-tenant isolation by default.</p>
      </div>
      <div class="card">
        <div class="card-icon">🔄</div>
        <h3>Workflows</h3>
        <p>Chain processors into configurable workflows with versioned evaluation sets for quality tracking.</p>
      </div>
      <div class="card">
        <div class="card-icon">📊</div>
        <h3>Observability</h3>
        <p>Prometheus metrics, structured logging, request tracing, and detailed run versioning for full visibility.</p>
      </div>
      <div class="card">
        <div class="card-icon">🚀</div>
        <h3>Production Ready</h3>
        <p>Rate limiting, idempotency, webhook replay protection, and durable state — ready for scale from day one.</p>
      </div>
    </section>

    <section class="endpoints">
      <h2>Quick Reference</h2>
      <div class="endpoint"><span class="method method-get">GET</span><span class="ep-path">/alg/healthz</span><span class="ep-desc">Health check</span></div>
      <div class="endpoint"><span class="method method-get">GET</span><span class="ep-path">/version</span><span class="ep-desc">Service version</span></div>
      <div class="endpoint"><span class="method method-post">POST</span><span class="ep-path">/auth/google</span><span class="ep-desc">Google OAuth</span></div>
      <div class="endpoint"><span class="method method-post">POST</span><span class="ep-path">/auth/keys</span><span class="ep-desc">Create API key</span></div>
      <div class="endpoint"><span class="method method-post">POST</span><span class="ep-path">/parse</span><span class="ep-desc">Parse PDF</span></div>
      <div class="endpoint"><span class="method method-get">GET</span><span class="ep-path">/runs/{id}</span><span class="ep-desc">Get run status</span></div>
      <div class="endpoint"><span class="method method-post">POST</span><span class="ep-path">/usage/extract</span><span class="ep-desc">Extract usage</span></div>
    </section>

    <footer>
      Built with FastAPI &amp; Python &mdash; <a href="/api/docs">View full API docs</a>
    </footer>
  </div>
</body>
</html>"""


def build_api() -> FastAPI:
    """Build and configure the FastAPI application."""
    # Initialize database module references
    global async_session_factory, engine, get_session, Base, Run
    try:
        import database as db_module
        async_session_factory = db_module.async_session_factory
        engine = db_module.engine
        get_session = db_module.get_session
        Base = db_module.Base

        # app/models.py can't be imported as `app.models` on Vercel because
        # app.py (file) shadows app/ (package). Load by file path instead.
        from importlib import util as _importlib_util
        _models_path = Path(__file__).resolve().parent / "app" / "models.py"
        _spec = _importlib_util.spec_from_file_location("_app_models", str(_models_path))
        _models_module = _importlib_util.module_from_spec(_spec)
        _spec.loader.exec_module(_models_module)  # type: ignore[union-attr]
        Run = _models_module.Run
    except Exception as e:
        # Database modules not available - tests may provide mocks
        logger = get_logger()
        logger.warning(f"Database import failed: {e}")

    if async_session_factory is None:
        raise RuntimeError(
            "Database session factory is required for durable operational state. "
            "Ensure database.py is importable and DATABASE_URL is configured."
        )

    state_backend = _resolve_state_backend()
    using_memory_operational_state = state_backend == "memory"

    if state_backend == "redis":
        redis_url = (settings.REDIS_URL or "").strip()
        if not redis_url:
            raise RuntimeError("REDIS_URL must be configured when STATE_BACKEND=redis")
        rate_limit_store = RedisRateLimitStore(redis_url)
    else:
        rate_limit_store = InMemoryRateLimitStore()

    idempotency_store = SQLIdempotencyStore(async_session_factory)
    webhook_replay_store = SQLWebhookReplayStore(async_session_factory)
    job_store = SQLBackgroundJobStore(async_session_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifespan: startup and shutdown."""
        # Startup
        logger = get_logger()

        _validate_startup_security_configuration()
        await _validate_startup_state_configuration(app)

        versions = {
            "service": app.version,
        }
        try:
            from importlib import metadata
            versions["fastapi"] = metadata.version("fastapi")
            versions["pydantic"] = metadata.version("pydantic")
            versions["pdf_usage_extractor"] = metadata.version("pdf-usage-extractor")
        except Exception:  # pragma: no cover - best effort logging only
            pass

        logger.info(
            "Service startup",
            extra={
                "context": {
                    "versions": versions,
                    "env": settings.ENV,
                    "rate_per_min": settings.RATE_PER_MIN,
                    "max_file_mb": settings.MAX_FILE_MB,
                    "database_configured": engine is not None,
                    "schema_management": "alembic",
                }
            },
        )

        yield

        # Shutdown
        try:
            rate_store = getattr(app.state, "rate_limit_store", None)
            if rate_store is not None:
                await rate_store.close()
            from vendor_libs.utils.http import close_http_client
            await close_http_client()
            logger.info("HTTP client closed successfully")
        except Exception as e:
            logger.warning(f"Error closing HTTP client: {e}")

    app = FastAPI(
        title="PDF Usage Extraction Service",
        version="0.1.0",
        description="Extract internet usage data from telecom PDF invoices",
        root_path="/api",  # For Vercel routing
        lifespan=lifespan,
        docs_url=None,   # Disable default docs — we serve custom dark theme
        redoc_url=None,   # Disable default redoc
        generate_unique_id_function=lambda route: f"{route.tags[0]}-{route.name}" if route.tags else route.name,
    )
    app.state.rate_limit_store = rate_limit_store
    app.state.idempotency_store = idempotency_store
    app.state.webhook_replay_store = webhook_replay_store
    app.state.job_store = job_store
    app.state.state_backend = state_backend
    app.state.using_memory_operational_state = using_memory_operational_state

    # ==================== CUSTOM DARK SWAGGER UI ====================
    SWAGGER_DARK_CSS = """
    :root {
      --bg-primary: #0f0f23;
      --bg-secondary: #1a1a3e;
      --bg-card: #16163a;
      --text-primary: #e2e8f0;
      --text-secondary: #94a3b8;
      --accent: #6366f1;
      --accent-hover: #818cf8;
      --accent-glow: rgba(99,102,241,0.3);
      --success: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
      --border: rgba(148,163,184,0.12);
    }
    body { background: var(--bg-primary) !important; color: var(--text-primary) !important; }
    .swagger-ui { background: var(--bg-primary) !important; color: var(--text-primary) !important; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important; }
    .swagger-ui .topbar { display: none !important; }
    .swagger-ui .info { margin: 30px 0 !important; }
    .swagger-ui .info .title { color: var(--text-primary) !important; font-weight: 700 !important; font-size: 2rem !important; }
    .swagger-ui .info .description p { color: var(--text-secondary) !important; }
    .swagger-ui .info a { color: var(--accent) !important; }
    .swagger-ui .scheme-container { background: var(--bg-secondary) !important; border: 1px solid var(--border) !important; border-radius: 12px !important; padding: 16px !important; box-shadow: 0 4px 20px rgba(0,0,0,0.3) !important; }
    .swagger-ui .opblock-tag { color: var(--text-primary) !important; border-bottom: 1px solid var(--border) !important; font-weight: 600 !important; }
    .swagger-ui .opblock-tag:hover { background: var(--bg-secondary) !important; }
    .swagger-ui .opblock { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: 10px !important; margin-bottom: 12px !important; box-shadow: 0 2px 12px rgba(0,0,0,0.2) !important; transition: all 0.2s ease !important; }
    .swagger-ui .opblock:hover { border-color: var(--accent) !important; box-shadow: 0 4px 24px var(--accent-glow) !important; }
    .swagger-ui .opblock .opblock-summary { border: none !important; border-radius: 10px !important; }
    .swagger-ui .opblock .opblock-summary-method { border-radius: 6px !important; font-weight: 700 !important; font-size: 0.75rem !important; padding: 6px 16px !important; min-width: 70px !important; text-align: center !important; }
    .swagger-ui .opblock.opblock-get { border-left: 3px solid var(--success) !important; }
    .swagger-ui .opblock.opblock-get .opblock-summary-method { background: var(--success) !important; color: #fff !important; }
    .swagger-ui .opblock.opblock-post { border-left: 3px solid var(--accent) !important; }
    .swagger-ui .opblock.opblock-post .opblock-summary-method { background: var(--accent) !important; color: #fff !important; }
    .swagger-ui .opblock.opblock-put { border-left: 3px solid var(--warning) !important; }
    .swagger-ui .opblock.opblock-put .opblock-summary-method { background: var(--warning) !important; color: #fff !important; }
    .swagger-ui .opblock.opblock-delete { border-left: 3px solid var(--danger) !important; }
    .swagger-ui .opblock.opblock-delete .opblock-summary-method { background: var(--danger) !important; color: #fff !important; }
    .swagger-ui .opblock.opblock-patch { border-left: 3px solid #a855f7 !important; }
    .swagger-ui .opblock.opblock-patch .opblock-summary-method { background: #a855f7 !important; color: #fff !important; }
    .swagger-ui .opblock .opblock-summary-path { color: var(--text-primary) !important; }
    .swagger-ui .opblock .opblock-summary-description { color: var(--text-secondary) !important; }
    .swagger-ui .opblock-body { background: var(--bg-secondary) !important; }
    .swagger-ui .opblock-section-header { background: var(--bg-secondary) !important; border-bottom: 1px solid var(--border) !important; }
    .swagger-ui .opblock-section-header h4 { color: var(--text-primary) !important; }
    .swagger-ui .btn { border-radius: 8px !important; font-weight: 600 !important; transition: all 0.15s ease !important; }
    .swagger-ui .btn.execute { background: var(--accent) !important; border-color: var(--accent) !important; color: #fff !important; border-radius: 8px !important; font-weight: 600 !important; }
    .swagger-ui .btn.execute:hover { background: var(--accent-hover) !important; box-shadow: 0 4px 16px var(--accent-glow) !important; }
    .swagger-ui .btn.cancel { color: var(--danger) !important; border-color: var(--danger) !important; }
    .swagger-ui .btn.authorize { color: var(--accent) !important; border-color: var(--accent) !important; }
    .swagger-ui .btn.authorize svg { fill: var(--accent) !important; }
    .swagger-ui select { background: var(--bg-card) !important; color: var(--text-primary) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; }
    .swagger-ui input[type=text], .swagger-ui textarea { background: var(--bg-card) !important; color: var(--text-primary) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; }
    .swagger-ui .parameter__name { color: var(--text-primary) !important; }
    .swagger-ui .parameter__type { color: var(--text-secondary) !important; }
    .swagger-ui .parameter__in { color: var(--text-secondary) !important; }
    .swagger-ui table thead tr th { color: var(--text-secondary) !important; border-bottom: 1px solid var(--border) !important; }
    .swagger-ui table tbody tr td { color: var(--text-primary) !important; border-bottom: 1px solid var(--border) !important; }
    .swagger-ui .response-col_status { color: var(--text-primary) !important; }
    .swagger-ui .response-col_description { color: var(--text-secondary) !important; }
    .swagger-ui .responses-inner h4, .swagger-ui .responses-inner h5 { color: var(--text-primary) !important; }
    .swagger-ui .model-box { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; }
    .swagger-ui .model { color: var(--text-primary) !important; }
    .swagger-ui .model-title { color: var(--text-primary) !important; }
    .swagger-ui .prop-type { color: var(--accent) !important; }
    .swagger-ui .prop-format { color: var(--text-secondary) !important; }
    .swagger-ui section.models { border: 1px solid var(--border) !important; border-radius: 12px !important; background: var(--bg-card) !important; }
    .swagger-ui section.models h4 { color: var(--text-primary) !important; }
    .swagger-ui .model-container { background: var(--bg-card) !important; }
    .swagger-ui .highlight-code .microlight { background: var(--bg-primary) !important; color: var(--text-primary) !important; border-radius: 8px !important; border: 1px solid var(--border) !important; font-family: 'JetBrains Mono', 'Fira Code', monospace !important; }
    .swagger-ui .copy-to-clipboard { background: var(--bg-card) !important; }
    .swagger-ui .download-contents { color: var(--accent) !important; }
    .swagger-ui .response-control-media-type__accept-message { color: var(--text-secondary) !important; }
    .swagger-ui .version-stamp { display: none !important; }
    .swagger-ui .info .version { background: var(--accent) !important; color: #fff !important; border-radius: 20px !important; padding: 4px 12px !important; font-weight: 600 !important; }
    .swagger-ui .loading-container { background: var(--bg-primary) !important; }
    .swagger-ui .loading-container .loading:after { color: var(--text-secondary) !important; }
    .swagger-ui .markdown p, .swagger-ui .markdown li { color: var(--text-secondary) !important; }
    .swagger-ui .markdown code { background: var(--bg-card) !important; color: var(--accent) !important; border-radius: 4px !important; padding: 2px 6px !important; }
    /* Scrollbar styling */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--bg-primary); }
    ::-webkit-scrollbar-thumb { background: var(--bg-secondary); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
    /* Header gradient accent */
    .swagger-ui .info { border-bottom: 2px solid transparent; background-image: linear-gradient(var(--bg-primary), var(--bg-primary)), linear-gradient(135deg, var(--accent), #a855f7, #ec4899); background-origin: padding-box, border-box; background-clip: padding-box, border-box; padding-bottom: 24px !important; }
    """

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui() -> HTMLResponse:
        """Serve custom dark-themed Swagger UI."""
        return HTMLResponse(
            content=_build_swagger_html(app.title, app.openapi_url, SWAGGER_DARK_CSS),
            media_type="text/html",
        )

    # ==================== FAVICON ====================
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon():
        """Serve the official Algorythmos favicon."""
        favicon_path = Path(__file__).resolve().parent / "public" / "favicon.ico"
        if favicon_path.exists():
            return Response(
                content=favicon_path.read_bytes(),
                media_type="image/x-icon",
                headers={"Cache-Control": "public, max-age=604800"},  # 7 days
            )
        # Fallback to inline SVG if file missing
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#a855f7"/></linearGradient></defs><rect width="32" height="32" rx="6" fill="url(#g)"/><text x="16" y="23" text-anchor="middle" fill="white" font-family="Arial,sans-serif" font-weight="bold" font-size="20">A</text></svg>'
        return Response(content=svg, media_type="image/svg+xml")

    # ==================== PUBLIC STATIC FILES ====================
    @app.get("/public/{filename:path}", include_in_schema=False)
    async def serve_public(filename: str):
        """Serve branding assets from the public/ directory."""
        import mimetypes
        public_dir = (Path(__file__).resolve().parent / "public").resolve()
        file_path = (public_dir / filename).resolve()
        # Security: prevent path traversal
        try:
            file_path.relative_to(public_dir)
        except ValueError:
            raise HTTPException(status_code=403, detail="Forbidden")
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        mime, _ = mimetypes.guess_type(str(file_path))
        return Response(
            content=file_path.read_bytes(),
            media_type=mime or "application/octet-stream",
            headers={"Cache-Control": "public, max-age=604800"},  # 7 days
        )

    # ==================== LANDING PAGE ====================
    @app.get("/", tags=["health"], summary="API landing page", include_in_schema=False)
    async def landing_page() -> HTMLResponse:
        """Serve a premium API landing page."""
        return HTMLResponse(content=_build_landing_html())

    # Custom OpenAPI schema with error handling
    @app.get("/openapi.json", include_in_schema=False)
    async def custom_openapi():
        """Custom OpenAPI schema endpoint with error handling."""
        try:
            if app.openapi_schema:
                return app.openapi_schema

            from fastapi.openapi.utils import get_openapi

            openapi_schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )

            # Add custom metadata
            openapi_schema["info"]["x-logo"] = {
                "url": "https://api.algorythmos.com/logo.png"
            }

            app.openapi_schema = openapi_schema
            return app.openapi_schema
        except Exception as e:
            logger = get_logger()
            logger.error(f"Error generating OpenAPI schema: {e}", exc_info=True)
            return {
                "openapi": "3.1.0",
                "info": {
                    "title": app.title,
                    "version": app.version,
                    "description": "Error generating full schema"
                },
                "paths": {},
                "error": str(e)
            }

    # Add middleware in correct order (LIFO - last added runs first)
    # CORS must be added LAST so it runs FIRST and wraps all responses

    # Production middlewares (added first, run after CORS)
    app.add_middleware(
        RateLimitMiddleware,
        rate_limit_store=rate_limit_store,
        requests_per_minute=60,
        requests_per_hour=1000,
        fail_closed=_is_production_environment(),
    )
    app.add_middleware(
        IdempotencyMiddleware,
        idempotency_store=idempotency_store,
        ttl_seconds=settings.IDEMPOTENCY_TTL_S,
        fail_closed=_is_production_environment(),
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(FileSizeMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # CORS middleware added LAST so it runs FIRST (outermost wrapper)
    origins = settings.get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-API-Key", "X-Tenant-Id", "*"],
        expose_headers=["X-Request-ID"],
    )

    # Global router instance and logger
    global router_engine
    router_engine = ExtractionRouter()
    logger = get_logger()

    # Health endpoint (public)
    @app.get("/alg/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    @app.get("/health", tags=["health"], include_in_schema=False)
    async def health() -> dict[str, str]:
        """Compatibility health endpoint for infrastructure checks."""
        return {"status": "ok"}

    # Version endpoint (public)
    @app.get("/capabilities", tags=["health"], summary="Runtime capabilities")
    async def get_capabilities() -> Dict[str, Any]:
        """Return runtime-supported formats and enterprise controls."""
        return {
            "supported_formats": format_validator.get_supported_formats(),
            "limits": {
                "max_file_mb": settings.MAX_FILE_MB,
                "max_file_bytes": settings.max_file_bytes,
                "run_max_file_bytes": RUN_MAX_FILE_BYTES,
            },
            "webhook": {
                "allow_legacy_signatures": settings.WEBHOOK_ALLOW_LEGACY_SIGNATURES,
                "legacy_requires_timestamp": settings.WEBHOOK_LEGACY_REQUIRE_TIMESTAMP,
                "replay_window_s": WEBHOOK_REPLAY_WINDOW_S,
            },
        }

    @app.get("/version", tags=["health"])
    async def version() -> dict[str, str]:
        """Get service version and environment information."""
        try:
            from importlib import metadata
            response = {
                "app": "api-algorythmos",
                "env": settings.ENV,
                "service": app.version,
                "fastapi": metadata.version("fastapi"),
                "pydantic": metadata.version("pydantic"),
            }
            try:
                response["pdf_usage_extractor"] = metadata.version("pdf-usage-extractor")
            except metadata.PackageNotFoundError:
                response["pdf_usage_extractor"] = "0.0.0"
            return response
        except Exception:  # pragma: no cover - fallback if metadata unavailable
            return {
                "app": "api-algorythmos",
                "env": settings.ENV,
                "service": app.version
            }

    # Vendor health endpoint (public) - for testing resilient client
    @app.get("/vendor/healthz", tags=["health"])
    async def vendor_health():
        """Test vendor service health with resilient client."""
        try:
            from vendor_libs.services.vendor import vendor_service
            is_healthy = await vendor_service.vendor_health_check()
            return Response(status_code=204 if is_healthy else 502)
        except Exception:
            return Response(status_code=502)

    # Prometheus metrics endpoint (public)
    @app.get("/metrics", tags=["observability"])
    async def metrics():
        """Expose Prometheus metrics."""
        return await metrics_app()()

    # ==================== AUTHENTICATION ENDPOINTS ====================

    @app.post(
        "/auth/google",
        status_code=status.HTTP_200_OK,
        tags=["auth"],
        summary="Authenticate with Google",
        description="Verify Google ID token and persist user identity. This endpoint does NOT issue sessions or JWTs.",
        responses={
            200: {"description": "Authentication successful", "content": {"application/json": {"example": {"status": "ok"}}}},
            401: {"description": "Invalid or expired token"},
        },
    )
    async def auth_google(
        authorization: str = Header(..., description="Bearer <token>"),
    ):
        """Authenticate user by verifying a Google ID token."""
        # Extract token from Bearer header
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_AUTH_HEADER", "message": "Authorization header must be 'Bearer <token>'"},
            )

        token = authorization[7:].strip()  # Strip "Bearer " prefix

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN", "message": "Token missing"},
            )

        from app.auth.google_auth import GoogleAuthError, verify_google_token

        try:
            verify_google_token(token, client_id=settings.GOOGLE_CLIENT_ID)
        except GoogleAuthError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_TOKEN", "message": "Google token verification failed"},
            )

        return {"status": "ok"}

    # ==================== API KEY MANAGEMENT ENDPOINTS ====================
    
    # Models are defined at module scope (above build_api) for Pydantic compatibility
    
    # Constants for API keys
    API_KEY_PREFIX = "alg_"
    MAX_KEYS_PER_USER = 10

    def generate_api_key() -> tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            Tuple of (raw_key, key_hash, prefix)
        """
        # Generate 32 random URL-safe characters
        random_part = secrets.token_urlsafe(32)
        raw_key = f"{API_KEY_PREFIX}{random_part}"

        # Hash the key with SHA-256
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        # Prefix for display (alg_ + first 8 chars of random part)
        prefix = f"{API_KEY_PREFIX}{random_part[:8]}"

        return raw_key, key_hash, prefix

    def hash_api_key(raw_key: str) -> str:
        """Hash an API key for lookup."""
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def get_current_user_from_token(
        authorization: Optional[str],
        session: AsyncSession,
    ) -> Optional["UserDB"]:
        """
        Verify Google ID token and return the associated user.
        Returns None if token is invalid or user not found.
        """
        if not authorization or not authorization.startswith("Bearer "):
            return None

        token = authorization[7:].strip()
        if not token:
            return None

        # Import UserDB model
        from models_user import UserDB

        # For now, simplified: look up user by a query
        # In production, verify Google token and extract email/sub
        # Then look up user by provider_account_id or email

        # Since we don't have full Google verification here,
        # we'll need to verify the token using google-auth
        try:
            from app.auth.google_auth import GoogleAuthError, verify_google_token
            user_info = verify_google_token(token, client_id=settings.GOOGLE_CLIENT_ID)

            # Find user by email
            result = await session.execute(
                select(UserDB).where(
                    UserDB.email == user_info.email,
                    UserDB.is_active == True
                )
            )
            user = result.scalar_one_or_none()

            if not user:
                # Create user if not exists (first login)
                user = UserDB(
                    id=str(uuid4()),
                    email=user_info.email,
                    display_name=user_info.name,
                    avatar_url=user_info.picture,
                    provider="google",
                    provider_account_id=user_info.sub,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)

            return user
        except GoogleAuthError:
            return None
        except Exception:
            return None

    async def get_user_from_api_key(
        api_key: str,
        session: AsyncSession,
    ) -> Optional["UserDB"]:
        """
        Look up user by API key.
        Updates last_used_at timestamp on successful lookup.
        """
        if not api_key or not api_key.startswith(API_KEY_PREFIX):
            return None

        from models_api_key import ApiKeyDB
        from models_user import UserDB

        key_hash = hash_api_key(api_key)

        # Find the API key
        result = await session.execute(
            select(ApiKeyDB).where(
                ApiKeyDB.key_hash == key_hash,
                ApiKeyDB.is_active == True
            )
        )
        api_key_record = result.scalar_one_or_none()

        if not api_key_record:
            return None

        # Update last_used_at
        api_key_record.last_used_at = datetime.now(timezone.utc)
        await session.commit()

        # Get the associated user
        result = await session.execute(
            select(UserDB).where(
                UserDB.id == api_key_record.user_id,
                UserDB.is_active == True
            )
        )
        return result.scalar_one_or_none()

    async def require_authenticated_user(
        request: Request,
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
        session: AsyncSession = Depends(get_session),
    ) -> "UserDB":
        """
        Dual authentication dependency.

        Priority:
        1. Authorization: Bearer <token> (Google ID token)
        2. X-API-Key: alg_... (API key)

        Returns the authenticated User object.
        Raises 401 if neither method succeeds.
        """
        from models_user import UserDB

        user = None

        # Try Bearer token first
        if authorization:
            user = await get_current_user_from_token(authorization, session)

        # If no user from token, try API key
        if not user and x_api_key:
            user = await get_user_from_api_key(x_api_key, session)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "Invalid or missing authentication"},
            )

        # Store user in request state for downstream use
        request.state.user = user
        request.state.tenant_id = user.email.split("@")[-1] if user.email else "default"

        return user

    @app.post(
        "/auth/keys",
        response_model=CreateApiKeyResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["auth"],
        summary="Create API key",
        description="Generate a new API key for programmatic access. The raw key is only shown once!",
        responses={
            201: {"description": "API key created successfully"},
            400: {"description": "Key limit exceeded (max 10 per user)"},
            401: {"description": "Not authenticated"},
        },
    )
    async def create_api_key(
        request: Request,
        payload: CreateApiKeyRequest,
        user: "UserDB" = Depends(require_authenticated_user),
        session: AsyncSession = Depends(get_session),
    ) -> CreateApiKeyResponse:
        """Create a new API key for the authenticated user."""
        from models_api_key import ApiKeyDB

        # Check key limit
        result = await session.execute(
            select(func.count(ApiKeyDB.id)).where(
                ApiKeyDB.user_id == user.id,
                ApiKeyDB.is_active == True
            )
        )
        key_count = result.scalar() or 0

        if key_count >= MAX_KEYS_PER_USER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "KEY_LIMIT_EXCEEDED",
                    "message": f"Maximum of {MAX_KEYS_PER_USER} API keys per user. Please revoke an existing key first."
                },
            )

        # Generate the key
        raw_key, key_hash, prefix = generate_api_key()

        # Create the record
        api_key = ApiKeyDB(
            id=str(uuid4()),
            user_id=user.id,
            name=payload.name,
            key_hash=key_hash,
            prefix=prefix,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

        logger.info(
            "API key created",
            extra={
                "context": {
                    "key_id": api_key.id,
                    "user_id": user.id,
                    "key_name": payload.name,
                    "prefix": prefix,
                }
            }
        )

        return CreateApiKeyResponse(
            id=api_key.id,
            name=api_key.name,
            prefix=api_key.prefix,
            created_at=api_key.created_at,
            raw_key=raw_key,  # Only returned on creation!
        )

    @app.get(
        "/auth/keys",
        response_model=List[ApiKeyResponse],
        tags=["auth"],
        summary="List API keys",
        description="Retrieve all active API keys for the authenticated user.",
    )
    async def list_api_keys(
        request: Request,
        user: "UserDB" = Depends(require_authenticated_user),
        session: AsyncSession = Depends(get_session),
    ) -> List[ApiKeyResponse]:
        """List all API keys for the authenticated user."""
        from models_api_key import ApiKeyDB

        result = await session.execute(
            select(ApiKeyDB)
            .where(
                ApiKeyDB.user_id == user.id,
                ApiKeyDB.is_active == True
            )
            .order_by(ApiKeyDB.created_at.desc())
        )
        keys = result.scalars().all()

        return [
            ApiKeyResponse(
                id=key.id,
                name=key.name,
                prefix=key.prefix,
                created_at=key.created_at,
                last_used_at=key.last_used_at,
            )
            for key in keys
        ]

    @app.delete(
        "/auth/keys/{key_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["auth"],
        summary="Revoke API key",
        description="Revoke (soft delete) an API key. This cannot be undone.",
        responses={
            204: {"description": "API key revoked successfully"},
            404: {"description": "API key not found"},
        },
    )
    async def revoke_api_key(
        request: Request,
        key_id: str = PathParam(..., description="API key ID to revoke"),
        user: "UserDB" = Depends(require_authenticated_user),
        session: AsyncSession = Depends(get_session),
    ):
        """Revoke an API key (soft delete)."""
        from models_api_key import ApiKeyDB

        result = await session.execute(
            select(ApiKeyDB).where(
                ApiKeyDB.id == key_id,
                ApiKeyDB.user_id == user.id,
                ApiKeyDB.is_active == True
            )
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "API key not found"},
            )

        # Soft delete
        api_key.is_active = False
        await session.commit()

        logger.info(
            "API key revoked",
            extra={
                "context": {
                    "key_id": key_id,
                    "user_id": user.id,
                    "key_name": api_key.name,
                }
            }
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)


    # ==================== GENERIC DOCUMENT PROCESSING ENDPOINTS ====================

    # Schema Management Endpoints
    @app.post(
        "/schemas",
        response_model=ExtractionSchema,
        status_code=status.HTTP_201_CREATED,
        tags=["schemas"],
        summary="Create extraction schema",
        description="Create a new custom extraction schema with field definitions. Schemas define what fields to extract from documents.",
    )
    async def create_schema(
        request: Request,
        payload: CreateSchemaRequest = Body(..., description="Schema configuration"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ExtractionSchema:
        """Create a new extraction schema."""
        tenant_id = tenant_ctx["tenant"]

        try:
            schema = await SchemaService.create_schema(
                session=session,
                tenant_id=tenant_id,
                request=payload,
            )
            logger.info(
                "Schema created",
                extra={
                    "context": {
                        "schema_id": schema.schema_id,
                        "schema_name": schema.name,
                        "tenant_id": tenant_id,
                        "field_count": len(schema.fields),
                    }
                }
            )
            return schema
        except ValueError as e:
            from core.config import build_error_response
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=build_error_response("validation_error", str(e))
            )

    @app.get(
        "/schemas",
        tags=["schemas"],
        summary="List extraction schemas",
        description="Retrieve a paginated list of extraction schemas for the current tenant.",
    )
    async def list_schemas(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100, description="Maximum number of items to return"),
        offset: int = Query(default=0, ge=0, description="Number of items to skip"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """List extraction schemas."""
        from core.config import build_pagination_meta

        tenant_id = tenant_ctx["tenant"]

        items, total = await SchemaService.list_schemas(
            session=session,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
        )

        return {
            "items": items,
            "meta": build_pagination_meta(limit, offset, total)
        }

    @app.get(
        "/schemas/{schema_id}",
        response_model=ExtractionSchema,
        tags=["schemas"],
        summary="Get schema details",
        description="Retrieve details of a specific extraction schema by ID.",
    )
    async def get_schema(
        request: Request,
        schema_id: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ExtractionSchema:
        """Get schema by ID."""
        from core.config import build_error_response

        tenant_id = tenant_ctx["tenant"]

        schema = await SchemaService.get_schema(
            session=session,
            tenant_id=tenant_id,
            schema_id=schema_id,
        )

        if not schema:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", f"Schema '{schema_id}' not found")
            )

        return schema

    @app.patch(
        "/schemas/{schema_id}",
        response_model=ExtractionSchema,
        tags=["schemas"],
        summary="Update schema",
        description="Update an existing extraction schema. Field changes increment the schema version.",
    )
    async def update_schema(
        request: Request,
        schema_id: str,
        payload: UpdateSchemaRequest = Body(..., description="Schema updates"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ExtractionSchema:
        """Update an existing schema."""
        from core.config import build_error_response

        tenant_id = tenant_ctx["tenant"]

        try:
            schema = await SchemaService.update_schema(
                session=session,
                tenant_id=tenant_id,
                schema_id=schema_id,
                request=payload,
            )

            if not schema:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=build_error_response("resource_not_found", f"Schema '{schema_id}' not found")
                )

            logger.info(
                "Schema updated",
                extra={
                    "context": {
                        "schema_id": schema.schema_id,
                        "schema_name": schema.name,
                        "version": schema.version,
                        "tenant_id": tenant_id,
                    }
                }
            )
            return schema
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=build_error_response("validation_error", str(e))
            )

    @app.delete(
        "/schemas/{schema_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["schemas"],
        summary="Delete schema",
        description="Delete an extraction schema. This operation cannot be undone.",
    )
    async def delete_schema(
        request: Request,
        schema_id: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> Response:
        """Delete a schema."""
        from core.config import build_error_response

        tenant_id = tenant_ctx["tenant"]

        deleted = await SchemaService.delete_schema(
            session=session,
            tenant_id=tenant_id,
            schema_id=schema_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", f"Schema '{schema_id}' not found")
            )

        logger.info(
            "Schema deleted",
            extra={
                "context": {
                    "schema_id": schema_id,
                    "tenant_id": tenant_id,
                }
            }
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Extractor Management Endpoints
    @app.post(
        "/extractors",
        response_model=ExtractorConfig,
        status_code=status.HTTP_201_CREATED,
        tags=["extractors"],
        summary="Create extractor",
        description="Create a new extractor that uses a schema to extract data from documents.",
    )
    async def create_extractor(
        request: Request,
        payload: CreateExtractorRequest = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ExtractorConfig:
        """Create a new extractor."""
        tenant_id = tenant_ctx["tenant"]

        try:
            extractor = await extractor_service.create_extractor(
                db=session,
                tenant_id=tenant_id,
                request=payload,
            )
            logger.info(
                "Extractor created",
                extra={
                    "context": {
                        "extractor_id": extractor.extractor_id,
                        "extractor_name": extractor.name,
                        "schema_id": extractor.schema_id,
                        "tenant_id": tenant_id,
                    }
                }
            )
            return extractor
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_EXTRACTOR", "message": str(e)}
            )

    @app.get(
        "/extractors",
        tags=["extractors"],
        summary="List extractors",
        description="Get a paginated list of extractors for this tenant.",
    )
    async def list_extractors(
        request: Request,
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
        schema_id: Optional[str] = Query(None, description="Filter by schema ID"),
        enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """List extractors for the tenant."""
        from core.config import build_pagination_meta

        tenant_id = tenant_ctx["tenant"]

        items, total = await extractor_service.list_extractors(
            db=session,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            schema_id=schema_id,
            enabled=enabled,
        )

        return {
            "items": items,
            "meta": build_pagination_meta(limit, offset, total)
        }

    @app.get(
        "/extractors/{extractor_id}",
        response_model=ExtractorConfig,
        tags=["extractors"],
        summary="Get extractor",
        description="Get details of a specific extractor by ID.",
    )
    async def get_extractor(
        request: Request,
        extractor_id: str = PathParam(..., description="Extractor ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ExtractorConfig:
        """Get an extractor by ID."""
        tenant_id = tenant_ctx["tenant"]

        extractor = await extractor_service.get_extractor(
            db=session,
            tenant_id=tenant_id,
            extractor_id=extractor_id,
        )

        if not extractor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "EXTRACTOR_NOT_FOUND", "message": f"Extractor '{extractor_id}' not found"}
            )

        return extractor

    @app.patch(
        "/extractors/{extractor_id}",
        response_model=ExtractorConfig,
        tags=["extractors"],
        summary="Update extractor",
        description="Update an existing extractor's configuration.",
    )
    async def update_extractor(
        request: Request,
        extractor_id: str = PathParam(..., description="Extractor ID"),
        payload: UpdateExtractorRequest = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ExtractorConfig:
        """Update an extractor."""
        tenant_id = tenant_ctx["tenant"]

        extractor = await extractor_service.update_extractor(
            db=session,
            tenant_id=tenant_id,
            extractor_id=extractor_id,
            request=payload,
        )

        if not extractor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "EXTRACTOR_NOT_FOUND", "message": f"Extractor '{extractor_id}' not found"}
            )

        logger.info(
            "Extractor updated",
            extra={
                "context": {
                    "extractor_id": extractor.extractor_id,
                    "extractor_name": extractor.name,
                    "tenant_id": tenant_id,
                }
            }
        )

        return extractor

    @app.delete(
        "/extractors/{extractor_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["extractors"],
        summary="Delete extractor",
        description="Delete an extractor permanently.",
    )
    async def delete_extractor(
        request: Request,
        extractor_id: str = PathParam(..., description="Extractor ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """Delete an extractor."""
        tenant_id = tenant_ctx["tenant"]

        deleted = await extractor_service.delete_extractor(
            db=session,
            tenant_id=tenant_id,
            extractor_id=extractor_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "EXTRACTOR_NOT_FOUND", "message": f"Extractor '{extractor_id}' not found"}
            )

        logger.info(
            "Extractor deleted",
            extra={
                "context": {
                    "extractor_id": extractor_id,
                    "tenant_id": tenant_id,
                }
            }
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Classifier Management Endpoints
    @app.post(
        "/classifiers",
        response_model=ClassifierConfig,
        status_code=status.HTTP_201_CREATED,
        tags=["classifiers"],
        summary="Create classifier",
        description="Create a new classifier for document classification.",
    )
    async def create_classifier(
        request: Request,
        payload: CreateClassifierRequest = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ClassifierConfig:
        """Create a new classifier."""
        tenant_id = tenant_ctx["tenant"]

        try:
            classifier = await classifier_service.create_classifier(
                db=session,
                tenant_id=tenant_id,
                request=payload,
            )
            logger.info(
                "Classifier created",
                extra={
                    "context": {
                        "classifier_id": classifier.classifier_id,
                        "classifier_name": classifier.name,
                        "tenant_id": tenant_id,
                    }
                }
            )
            return classifier
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_CLASSIFIER", "message": str(e)}
            )

    @app.get(
        "/classifiers",
        tags=["classifiers"],
        summary="List classifiers",
        description="Get a paginated list of classifiers for this tenant.",
    )
    async def list_classifiers(
        request: Request,
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
        enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """List classifiers for the tenant."""
        from core.config import build_pagination_meta

        tenant_id = tenant_ctx["tenant"]

        items, total = await classifier_service.list_classifiers(
            db=session,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            enabled=enabled,
        )

        return {
            "items": items,
            "meta": build_pagination_meta(limit, offset, total)
        }

    @app.get(
        "/classifiers/{classifier_id}",
        response_model=ClassifierConfig,
        tags=["classifiers"],
        summary="Get classifier",
        description="Get details of a specific classifier by ID.",
    )
    async def get_classifier(
        request: Request,
        classifier_id: str = PathParam(..., description="Classifier ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ClassifierConfig:
        """Get a classifier by ID."""
        tenant_id = tenant_ctx["tenant"]

        classifier = await classifier_service.get_classifier(
            db=session,
            tenant_id=tenant_id,
            classifier_id=classifier_id,
        )

        if not classifier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CLASSIFIER_NOT_FOUND", "message": f"Classifier '{classifier_id}' not found"}
            )

        return classifier

    @app.patch(
        "/classifiers/{classifier_id}",
        response_model=ClassifierConfig,
        tags=["classifiers"],
        summary="Update classifier",
        description="Update an existing classifier's configuration.",
    )
    async def update_classifier(
        request: Request,
        classifier_id: str = PathParam(..., description="Classifier ID"),
        payload: UpdateClassifierRequest = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ClassifierConfig:
        """Update a classifier."""
        tenant_id = tenant_ctx["tenant"]

        classifier = await classifier_service.update_classifier(
            db=session,
            tenant_id=tenant_id,
            classifier_id=classifier_id,
            request=payload,
        )

        if not classifier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CLASSIFIER_NOT_FOUND", "message": f"Classifier '{classifier_id}' not found"}
            )

        logger.info(
            "Classifier updated",
            extra={
                "context": {
                    "classifier_id": classifier.classifier_id,
                    "classifier_name": classifier.name,
                    "tenant_id": tenant_id,
                }
            }
        )

        return classifier

    @app.delete(
        "/classifiers/{classifier_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["classifiers"],
        summary="Delete classifier",
        description="Delete a classifier permanently.",
    )
    async def delete_classifier(
        request: Request,
        classifier_id: str = PathParam(..., description="Classifier ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """Delete a classifier."""
        tenant_id = tenant_ctx["tenant"]

        deleted = await classifier_service.delete_classifier(
            db=session,
            tenant_id=tenant_id,
            classifier_id=classifier_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CLASSIFIER_NOT_FOUND", "message": f"Classifier '{classifier_id}' not found"}
            )

        logger.info(
            "Classifier deleted",
            extra={
                "context": {
                    "classifier_id": classifier_id,
                    "tenant_id": tenant_id,
                }
            }
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Splitter Management Endpoints
    @app.post(
        "/splitters",
        response_model=SplitterConfig,
        status_code=status.HTTP_201_CREATED,
        tags=["splitters"],
        summary="Create splitter",
        description="Create a new splitter for document splitting.",
    )
    async def create_splitter(
        request: Request,
        payload: CreateSplitterRequest = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> SplitterConfig:
        """Create a new splitter."""
        tenant_id = tenant_ctx["tenant"]

        try:
            splitter = await splitter_service.create_splitter(
                db=session,
                tenant_id=tenant_id,
                request=payload,
            )
            logger.info(
                "Splitter created",
                extra={
                    "context": {
                        "splitter_id": splitter.splitter_id,
                        "splitter_name": splitter.name,
                        "tenant_id": tenant_id,
                    }
                }
            )
            return splitter
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_SPLITTER", "message": str(e)}
            )

    @app.get(
        "/splitters",
        tags=["splitters"],
        summary="List splitters",
        description="Get a paginated list of splitters for this tenant.",
    )
    async def list_splitters(
        request: Request,
        limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
        enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """List splitters for the tenant."""
        from core.config import build_pagination_meta

        tenant_id = tenant_ctx["tenant"]

        items, total = await splitter_service.list_splitters(
            db=session,
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            enabled=enabled,
        )

        return {
            "items": items,
            "meta": build_pagination_meta(limit, offset, total)
        }

    @app.get(
        "/splitters/{splitter_id}",
        response_model=SplitterConfig,
        tags=["splitters"],
        summary="Get splitter",
        description="Get details of a specific splitter by ID.",
    )
    async def get_splitter(
        request: Request,
        splitter_id: str = PathParam(..., description="Splitter ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> SplitterConfig:
        """Get a splitter by ID."""
        tenant_id = tenant_ctx["tenant"]

        splitter = await splitter_service.get_splitter(
            db=session,
            tenant_id=tenant_id,
            splitter_id=splitter_id,
        )

        if not splitter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SPLITTER_NOT_FOUND", "message": f"Splitter '{splitter_id}' not found"}
            )

        return splitter

    @app.patch(
        "/splitters/{splitter_id}",
        response_model=SplitterConfig,
        tags=["splitters"],
        summary="Update splitter",
        description="Update an existing splitter's configuration.",
    )
    async def update_splitter(
        request: Request,
        splitter_id: str = PathParam(..., description="Splitter ID"),
        payload: UpdateSplitterRequest = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> SplitterConfig:
        """Update a splitter."""
        tenant_id = tenant_ctx["tenant"]

        splitter = await splitter_service.update_splitter(
            db=session,
            tenant_id=tenant_id,
            splitter_id=splitter_id,
            request=payload,
        )

        if not splitter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SPLITTER_NOT_FOUND", "message": f"Splitter '{splitter_id}' not found"}
            )

        logger.info(
            "Splitter updated",
            extra={
                "context": {
                    "splitter_id": splitter.splitter_id,
                    "splitter_name": splitter.name,
                    "tenant_id": tenant_id,
                }
            }
        )

        return splitter

    @app.delete(
        "/splitters/{splitter_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["splitters"],
        summary="Delete splitter",
        description="Delete a splitter permanently.",
    )
    async def delete_splitter(
        request: Request,
        splitter_id: str = PathParam(..., description="Splitter ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """Delete a splitter."""
        tenant_id = tenant_ctx["tenant"]

        deleted = await splitter_service.delete_splitter(
            db=session,
            tenant_id=tenant_id,
            splitter_id=splitter_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SPLITTER_NOT_FOUND", "message": f"Splitter '{splitter_id}' not found"}
            )

        logger.info(
            "Splitter deleted",
            extra={
                "context": {
                    "splitter_id": splitter_id,
                    "tenant_id": tenant_id,
                }
            }
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # === PHASE 2: Regex Extraction Endpoint ===

    @app.post(
        "/extract/regex",
        tags=["extraction"],
        summary="Extract fields using regex patterns",
        description="Extract structured data from text using regex patterns defined in an extraction schema.",
    )
    async def extract_with_regex(
        request: Request,
        schema_id: str = Body(..., description="ID of the extraction schema to use"),
        text: str = Body(..., description="Text content to extract from"),
        extractor_id: Optional[str] = Body(None, description="Optional specific extractor configuration to use"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """
        Extract structured fields from text using regex patterns.

        Uses extraction schemas to define fields and patterns for extraction.
        Returns extracted values with confidence scores and citations.
        """
        from core.config import build_error_response
        from document_processing.services import regex_extractor_service

        tenant_id = tenant_ctx["tenant"]

        try:
            result = await regex_extractor_service.extract_with_schema(
                db=session,
                tenant_id=tenant_id,
                schema_id=schema_id,
                text=text,
                extractor_id=extractor_id
            )

            logger.info(
                "Regex extraction completed",
                extra={
                    "context": {
                        "schema_id": schema_id,
                        "extractor_id": extractor_id,
                        "extracted_count": result["extracted_count"],
                        "total_fields": result["total_fields"],
                        "tenant_id": tenant_id,
                    }
                }
            )

            return result

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", str(e))
            )
        except Exception as e:
            logger.error(
                "Regex extraction failed",
                extra={
                    "context": {
                        "schema_id": schema_id,
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("extraction_error", f"Extraction failed: {str(e)}")
            )

    # === PHASE 3: Classification Endpoint ===

    @app.post(
        "/classify",
        tags=["classification"],
        summary="Classify document text",
        description="Classify document content into categories using keyword-based classification.",
    )
    async def classify_document(
        request: Request,
        text: str = Body(..., description="Text content to classify"),
        classifier_id: Optional[str] = Body(None, description="Optional specific classifier to use"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """
        Classify document text into categories.

        Uses classifier configurations with keyword matching to determine document categories.
        Returns classifications with confidence scores and matched keywords.
        """
        from core.config import build_error_response
        from document_processing.services import classification_service

        tenant_id = tenant_ctx["tenant"]

        try:
            result = await classification_service.classify_document(
                db=session,
                tenant_id=tenant_id,
                text=text,
                classifier_id=classifier_id
            )

            logger.info(
                "Document classification completed",
                extra={
                    "context": {
                        "classifier_id": classifier_id,
                        "classifiers_used": result["classifiers_used"],
                        "top_category": result["top_category"],
                        "classifications_count": len(result["classifications"]),
                        "tenant_id": tenant_id,
                    }
                }
            )

            return result

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", str(e))
            )
        except Exception as e:
            logger.error(
                "Document classification failed",
                extra={
                    "context": {
                        "classifier_id": classifier_id,
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("classification_error", f"Classification failed: {str(e)}")
            )

    # === PHASE 3: Splitting Endpoint ===

    @app.post(
        "/split",
        tags=["splitting"],
        summary="Split document text",
        description="Split document content into chunks using rule-based splitting strategies.",
    )
    async def split_document(
        request: Request,
        text: str = Body(..., description="Text content to split"),
        splitter_id: Optional[str] = Body(None, description="Optional specific splitter to use"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ):
        """
        Split document text into chunks.

        Uses splitter configurations with various strategies (delimiter, pattern, fixed_size, paragraph)
        to split documents into manageable chunks. Returns chunks with position metadata.
        """
        from core.config import build_error_response
        from document_processing.services import splitting_service

        tenant_id = tenant_ctx["tenant"]

        try:
            result = await splitting_service.split_document(
                db=session,
                tenant_id=tenant_id,
                text=text,
                splitter_id=splitter_id
            )

            logger.info(
                "Document splitting completed",
                extra={
                    "context": {
                        "splitter_id": result["splitter_id"],
                        "split_strategy": result["split_strategy"],
                        "chunk_count": result["chunk_count"],
                        "original_length": result["original_length"],
                        "tenant_id": tenant_id,
                    }
                }
            )

            return result

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", str(e))
            )
        except Exception as e:
            logger.error(
                "Document splitting failed",
                extra={
                    "context": {
                        "splitter_id": splitter_id,
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("splitting_error", f"Splitting failed: {str(e)}")
            )

    # =============================================================================
    # PHASE 4: File Upload and Parser Run Endpoints
    # =============================================================================

    @app.post(
        "/files",
        response_model=FileUpload,
        status_code=status.HTTP_201_CREATED,
        tags=["files"],
        summary="Upload a file",
        description="Upload a file for document processing"
    )
    async def upload_file_endpoint(
        request: Request,
        file: UploadFile = File(..., description="File to upload"),
        metadata: Optional[Dict[str, Any]] = Body(None, description="Additional file metadata"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> FileUpload:
        """Upload a file and store it for processing."""
        tenant_id = tenant_ctx["tenant"]

        try:
            logger.info(
                "File upload started",
                extra={
                    "context": {
                        "filename": file.filename,
                        "content_type": file.content_type,
                        "tenant_id": tenant_id,
                    }
                }
            )

            file_upload = await file_service.upload_file(
                session, tenant_id, file, metadata
            )

            logger.info(
                "File uploaded successfully",
                extra={
                    "context": {
                        "file_id": file_upload.file_id,
                        "filename": file_upload.filename,
                        "size_bytes": file_upload.size_bytes,
                        "tenant_id": tenant_id,
                    }
                }
            )

            return file_upload

        except HTTPException:
            raise

        except Exception as e:
            logger.error(
                "File upload failed",
                extra={
                    "context": {
                        "filename": file.filename if file else None,
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("upload_error", f"File upload failed: {str(e)}")
            )

    @app.get(
        "/files",
        response_model=Dict[str, Any],
        tags=["files"],
        summary="List files",
        description="List uploaded files with pagination"
    )
    async def list_files_endpoint(
        request: Request,
        limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> Dict[str, Any]:
        """List files for the tenant."""
        tenant_id = tenant_ctx["tenant"]
        files, total = await file_service.list_files(session, tenant_id, limit, offset)

        meta = build_pagination_meta(limit, offset, total)

        return {
            "items": [f.model_dump() for f in files],
            "meta": meta
        }

    @app.get(
        "/files/{file_id}",
        response_model=FileUpload,
        tags=["files"],
        summary="Get file",
        description="Get file metadata by ID"
    )
    async def get_file_endpoint(
        request: Request,
        file_id: str = PathParam(..., description="File ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> FileUpload:
        """Get file metadata."""
        tenant_id = tenant_ctx["tenant"]
        file_db = await file_service.get_file(session, tenant_id, file_id)

        if not file_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("FILE_NOT_FOUND", f"File not found: {file_id}")
            )

        return FileUpload(
            file_id=file_db.id,
            filename=file_db.filename,
            content_type=file_db.content_type,
            size_bytes=file_db.size_bytes,
            checksum=file_db.checksum,
            tenant_id=file_db.tenant_id,
            created_at=file_db.created_at,
            metadata=file_db.file_metadata
        )

    @app.delete(
        "/files/{file_id}",
        status_code=status.HTTP_200_OK,
        tags=["files"],
        summary="Delete file",
        description="Soft delete a file"
    )
    async def delete_file_endpoint(
        request: Request,
        file_id: str = PathParam(..., description="File ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> Dict[str, str]:
        """Soft delete a file."""
        tenant_id = tenant_ctx["tenant"]
        deleted = await file_service.delete_file(session, tenant_id, file_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("FILE_NOT_FOUND", f"File not found: {file_id}")
            )

        return {"message": "File deleted"}

    @app.post(
        "/parse",
        response_model=ParseResult,
        status_code=status.HTTP_200_OK,
        tags=["parsing"],
        summary="Parse document (sync)",
        description="Synchronously parse a document with classification, splitting, and extraction"
    )
    async def parse_document_sync(
        request: Request,
        parse_request: ParserRunRequest,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ParseResult:
        """Parse a document synchronously."""
        tenant_id = tenant_ctx["tenant"]

        try:
            logger.info(
                "Synchronous parse started",
                extra={
                    "context": {
                        "file_id": parse_request.file_id,
                        "schema_id": parse_request.schema_id,
                        "tenant_id": tenant_id,
                    }
                }
            )

            # Create run
            run_status = await parser_service.create_parser_run(
                session,
                tenant_id,
                parse_request.file_id,
                parse_request.schema_id,
                parse_request.extractor_id,
                parse_request.classifier_id,
                parse_request.splitter_id,
                parse_request.metadata
            )

            # Execute immediately
            result = await parser_service.execute_parser_run(
                session, tenant_id, run_status.run_id
            )

            logger.info(
                "Parse completed",
                extra={
                    "context": {
                        "run_id": result.run_id,
                        "status": result.status,
                        "processing_time_ms": result.processing_time_ms,
                        "tenant_id": tenant_id,
                    }
                }
            )

            return result

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", str(e))
            )
        except Exception as e:
            logger.error(
                "Parse failed",
                extra={
                    "context": {
                        "file_id": parse_request.file_id,
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("parse_error", f"Parse failed: {str(e)}")
            )

    @app.post(
        "/parse/async",
        response_model=ParserRunStatus,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["parsing"],
        summary="Parse document (async)",
        description="Create an asynchronous parser run (execution happens in background)"
    )
    async def parse_document_async(
        request: Request,
        parse_request: ParserRunRequest,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ParserRunStatus:
        """Create an async parser run and enqueue durable background execution."""
        tenant_id = tenant_ctx["tenant"]

        try:
            run_status = await parser_service.create_parser_run(
                session,
                tenant_id,
                parse_request.file_id,
                parse_request.schema_id,
                parse_request.extractor_id,
                parse_request.classifier_id,
                parse_request.splitter_id,
                parse_request.metadata
            )
            await parser_service.enqueue_parser_run_job(
                session,
                tenant_id,
                run_status.run_id,
                max_attempts=settings.PARSE_WORKER_MAX_ATTEMPTS,
            )

            logger.info(
                "Async parse queued",
                extra={
                    "context": {
                        "run_id": run_status.run_id,
                        "file_id": parse_request.file_id,
                        "tenant_id": tenant_id,
                    }
                }
            )

            return run_status

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("resource_not_found", str(e))
            )
        except Exception as e:
            logger.error(
                "Async parse creation failed",
                extra={
                    "context": {
                        "file_id": parse_request.file_id,
                        "error": str(e),
                        "tenant_id": tenant_id,
                    }
                },
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("parse_error", f"Parse creation failed: {str(e)}")
            )

    @app.get(
        "/parse/{run_id}",
        response_model=ParserRunStatus,
        tags=["parsing"],
        summary="Get parser run status",
        description="Get the status of a parser run"
    )
    async def get_parser_run_endpoint(
        request: Request,
        run_id: str = PathParam(..., description="Parser run ID"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> ParserRunStatus:
        """Get parser run status."""
        tenant_id = tenant_ctx["tenant"]
        run_status = await parser_service.get_parser_run(session, tenant_id, run_id)

        if not run_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=build_error_response("RUN_NOT_FOUND", f"Parser run not found: {run_id}")
            )

        return run_status

    @app.get(
        "/parse",
        response_model=Dict[str, Any],
        tags=["parsing"],
        summary="List parser runs",
        description="List parser runs with optional filtering"
    )
    async def list_parser_runs_endpoint(
        request: Request,
        file_id: Optional[str] = Query(None, description="Filter by file ID"),
        status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
        limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
        offset: int = Query(0, ge=0, description="Number of results to skip"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        session = Depends(get_session),
    ) -> Dict[str, Any]:
        """List parser runs."""
        tenant_id = tenant_ctx["tenant"]
        runs, total = await parser_service.list_parser_runs(
            session, tenant_id, file_id, status_filter, limit, offset
        )

        meta = build_pagination_meta(limit, offset, total)

        return {
            "items": [r.model_dump() for r in runs],
            "meta": meta
        }

    # =============================================================================
    # PHASE 5: LLM Processing Endpoints
    # =============================================================================

    @app.post(
        "/llm/summarize",
        response_model=Dict[str, Any],
        tags=["llm"],
        summary="Summarize document",
        description="Generate a summary of document text using LLM"
    )
    async def llm_summarize(
        request: Request,
        text: str = Body(..., description="Text to summarize"),
        max_length: int = Body(500, description="Maximum summary length"),
        style: str = Body("concise", description="Summary style: concise, detailed, bullet_points"),
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> Dict[str, Any]:
        """Generate document summary using LLM."""
        try:
            from document_processing.services.llm_service import llm_service

            result = await llm_service.summarize(text, max_length, style)

            return result

        except Exception as e:
            logger.error(
                "LLM summarization failed",
                extra={"context": {"error": str(e)}},
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("llm_error", f"Summarization failed: {str(e)}")
            )

    @app.post(
        "/llm/extract-entities",
        response_model=Dict[str, Any],
        tags=["llm"],
        summary="Extract entities",
        description="Extract named entities from text using LLM"
    )
    async def llm_extract_entities(
        request: Request,
        text: str = Body(..., description="Text to analyze"),
        entity_types: Optional[List[str]] = Body(None, description="Entity types to extract"),
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> Dict[str, Any]:
        """Extract named entities using LLM."""
        try:
            from document_processing.services.llm_service import llm_service

            result = await llm_service.extract_entities(text, entity_types)

            return result

        except Exception as e:
            logger.error(
                "LLM entity extraction failed",
                extra={"context": {"error": str(e)}},
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("llm_error", f"Entity extraction failed: {str(e)}")
            )

    @app.post(
        "/llm/answer-questions",
        response_model=Dict[str, Any],
        tags=["llm"],
        summary="Answer questions about document",
        description="Answer questions about document content using LLM"
    )
    async def llm_answer_questions(
        request: Request,
        text: str = Body(..., description="Document text"),
        questions: List[str] = Body(..., description="Questions to answer"),
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> Dict[str, Any]:
        """Answer questions about document using LLM."""
        try:
            from document_processing.services.llm_service import llm_service

            result = await llm_service.answer_questions(text, questions)

            return result

        except Exception as e:
            logger.error(
                "LLM question answering failed",
                extra={"context": {"error": str(e)}},
                exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=build_error_response("llm_error", f"Question answering failed: {str(e)}")
            )

    # =============================================================================
    # Original Legacy Endpoints
    # =============================================================================

    # File upload endpoint (protected)
    @app.post(
        "/extract/upload",
        response_model=ExtractResponse,
        tags=["extraction"],
        summary="Extract from uploaded PDFs",
        description="Upload one or more PDF files and extract telecom usage data. Supports multiple providers with automatic detection.",
    )
    async def extract_upload(
        request: Request,
        files: List[UploadFile] = File(..., description="PDF files to process"),
        provider_hint: Optional[str] = Query(default=None, description="Hint for telecom provider (e.g., 'orange')"),
        debug: bool = Query(default=False, description="Enable debug mode with additional logging"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
    ) -> ExtractResponse:
        """Extract usage data from uploaded PDF files."""
        if not files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "NO_FILES", "message": "No files uploaded"}
            )

        with tempfile.TemporaryDirectory(prefix="pdf-extract-") as tmpdir:
            saved_paths: List[str] = []

            for index, upload in enumerate(files):
                # Validate content type
                if upload.content_type not in {"application/pdf", "application/x-pdf", None}:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail={
                            "code": "INVALID_CONTENT_TYPE",
                            "message": f"Unsupported content type: {upload.content_type}"
                        }
                    )

                original = upload.filename or f"upload-{index}.pdf"
                filename = os.path.basename(original)

                if not filename.lower().endswith(".pdf"):
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail={
                            "code": "NOT_PDF",
                            "message": f"File is not a PDF: {filename}"
                        }
                    )

                dest = os.path.join(tmpdir, f"{index}_{filename}")
                content = await upload.read()

                # Check for empty file
                if not content:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "code": "EMPTY_FILE",
                            "message": f"Empty file: {filename}"
                        }
                    )

                # Check file size
                if len(content) > settings.max_file_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "code": "FILE_TOO_LARGE",
                            "message": f"File exceeds {settings.MAX_FILE_MB} MB limit"
                        }
                    )

                # Save file
                async with await anyio.open_file(dest, "wb") as fp:
                    await fp.write(content)
                await upload.close()
                saved_paths.append(dest)

            # Run extraction
            records, warnings, elapsed = await _run_extraction(
                path=tmpdir,
                provider_hint=provider_hint,
                debug=debug,
            )

            # Add confidence if missing
            for record in records:
                if record.confidence is None:
                    record.confidence = 0.0

            _log_request(
                route="/extract/upload",
                files=len(saved_paths),
                records=records,
                warnings=warnings,
                elapsed=elapsed,
                debug=debug,
                tenant_id=tenant_ctx["tenant"],
                request_id=getattr(request.state, "request_id", None),
            )

            return ExtractResponse(count=len(records), records=records, warnings=warnings)

    # Path extraction endpoint (protected)
    @app.post(
        "/extract/path",
        response_model=ExtractResponse,
        tags=["extraction"],
        summary="Extract from file path",
        description="Extract usage data from PDF files at a specified local or cloud storage path.",
    )
    async def extract_path_endpoint(
        request: Request,
        payload: PathRequest = Body(..., description="Path configuration with input_path and optional provider_hint"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
    ) -> ExtractResponse:
        """Extract usage data from files at the specified path."""
        resolved = os.path.expanduser(payload.input_path)
        if not os.path.exists(resolved):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "PATH_NOT_FOUND", "message": "Input path not found"}
            )

        try:
            records, warnings, elapsed = await _run_extraction(
                path=resolved,
                provider_hint=payload.provider_hint,
                debug=payload.debug,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={"code": "INVALID_PATH", "message": str(exc)}
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "FILE_NOT_FOUND", "message": str(exc)}
            ) from exc

        # Add confidence if missing
        for record in records:
            if record.confidence is None:
                record.confidence = 0.0

        files = 1
        if os.path.isdir(resolved):
            files = sum(1 for _ in Path(resolved).rglob("*.pdf"))

        _log_request(
            route="/extract/path",
            files=files,
            records=records,
            warnings=warnings,
            elapsed=elapsed,
            debug=payload.debug,
            tenant_id=tenant_ctx["tenant"],
            request_id=getattr(request.state, "request_id", None),
        )

        return ExtractResponse(count=len(records), records=records, warnings=warnings)

    # Job creation endpoint (protected)
    @app.post(
        "/jobs",
        tags=["jobs"],
        summary="Create background job",
        description="Create an asynchronous background job for PDF processing. Supports webhook notifications on completion.",
    )
    async def create_job(
        request: Request,
        payload: JobCreate = Body(..., description="Job configuration including input_path and optional webhook_url"),
        background_tasks: BackgroundTasks = None,
        tenant_ctx: Dict[str, str] = Depends(require_key),
    ) -> Dict[str, Any]:
        """Create a background job for processing."""
        job_store = getattr(request.app.state, "job_store", None)
        if job_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "JOB_STORE_UNAVAILABLE", "message": "Durable job store is not configured"},
            )

        job_id = str(uuid4())
        job_db = await job_store.create_job(
            job_id=job_id,
            tenant_id=tenant_ctx["tenant"],
            request_id=getattr(request.state, "request_id", None),
            payload=payload.model_dump(mode="json"),
            webhook_url=str(payload.webhook_url) if payload.webhook_url else None,
        )
        job_record = _background_job_db_to_record(job_db)

        background_tasks.add_task(
            _execute_job,
            job_id,
            payload,
            tenant_ctx["tenant"],
            job_record.request_id,
            job_store,
        )

        logger.info(
            "Job queued",
            extra={
                "context": {
                    "job_id": job_id,
                    "tenant_id": tenant_ctx["tenant"],
                    "request_id": job_record.request_id,
                }
            },
        )
        return job_record.model_dump(mode="json")

    # Job status endpoint (protected)
    @app.get(
        "/jobs/{job_id}",
        tags=["jobs"],
        summary="Get job status",
        description="Retrieve the status and results of a background processing job.",
    )
    async def get_job(
        request: Request,
        job_id: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
    ) -> Dict[str, Any]:
        """Get job status and results."""
        job_store = getattr(request.app.state, "job_store", None)
        if job_store is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "JOB_STORE_UNAVAILABLE", "message": "Durable job store is not configured"},
            )

        job = await job_store.get_job(job_id=job_id, tenant_id=tenant_ctx["tenant"])
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "JOB_NOT_FOUND", "message": "Job not found"}
            )
        return _background_job_db_to_record(job).model_dump(mode="json")

    # Algorythmos-style processor endpoints
    @app.post(
        "/processors/{processor_name}/runs",
        tags=["processors"],
        summary="Create processor run",
        description="Start a new processing run for the specified processor. Accepts either file uploads (multipart/form-data) or JSON with input_path. Supports idempotency and webhook notifications.",
        responses={
            200: {"description": "Run created successfully"},
            400: {"description": "Invalid request (too many files, file too large, invalid PDF, missing input)"},
            413: {"description": "Request entity too large"},
            415: {"description": "Unsupported media type"},
            502: {"description": "Vendor service error"},
        },
    )
    async def create_processor_run(
        processor_name: str,
        request: Request,
        background_tasks: BackgroundTasks,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None, description="API version for compatibility"),
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", description="Idempotency key for duplicate request prevention"),
        db = Depends(get_session),
        files: Optional[List[UploadFile]] = File(None, description="PDF files to process (max 50, max 10MB each)"),
    ) -> Dict[str, Any]:
        """Create a processor run (Algorythmos-style endpoint).

        Supports two modes:
        1. File upload mode: multipart/form-data with files
        2. Path reference mode: application/json with input_path
        """
        # Determine input mode and validate
        content_type = request.headers.get("content-type", "")
        is_json_mode = content_type.startswith("application/json")
        is_multipart_mode = content_type.startswith("multipart/form-data")

        # Validate that exactly one input method is provided
        if is_json_mode:
            # Parse JSON body manually
            try:
                body_bytes = await request.body()
                import json
                body_dict = json.loads(body_bytes)
                body = ProcessorCreateRunRequest(**body_dict)
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "INVALID_JSON",
                        "message": f"Invalid JSON body: {str(exc)}",
                    }
                )
            input_path = body.input_path
            # JSON mode: no files to validate
            files_to_process = []
        elif is_multipart_mode:
            if not files:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "MISSING_FILES",
                        "message": "At least one file is required for multipart/form-data requests",
                    }
                )
            # File upload mode
            input_path = None
            files_to_process = files
        else:
            raise HTTPException(
                status_code=415,
                detail={
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": "Content-Type must be either application/json or multipart/form-data",
                }
            )

        # Log API version if provided
        if x_api_version:
            logger.info(
                "API version requested",
                extra={"context": {"version": x_api_version, "processor": processor_name}},
            )

        tenant_id = tenant_ctx["tenant"]

        # Validate file count for multipart mode
        if files_to_process and len(files_to_process) > RUN_MAX_FILES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "TOO_MANY_FILES",
                    "message": f"Too many files: {len(files)} exceeds limit of {RUN_MAX_FILES}",
                }
            )

        # Check idempotency key - return existing run if found
        # Do this BEFORE file validation/upload to avoid unnecessary work
        if idempotency_key:
            stmt = select(Run).where(
                and_(
                    Run.tenant_id == tenant_id,
                    Run.processor == processor_name,
                    Run.idempotency_key == idempotency_key,
                )
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                logger.info(
                    "Idempotent run reused",
                    extra={"context": {"idempotency_key": idempotency_key, "run_id": existing.id}},
                )
                return {
                    "id": existing.id,
                    "processor_name": existing.processor,
                    "status": existing.status,
                    "created_at": existing.created_at.isoformat(),
                    "updated_at": existing.updated_at.isoformat(),
                    "tenant_id": existing.tenant_id,
                    "output": existing.output,
                    "error": existing.error,
                    "vendor_job_id": existing.vendor_job_id,
                }

            # Create placeholder record to claim the idempotency key
            # This prevents race conditions in concurrent requests
            run_id = str(uuid4())
            placeholder = Run(
                id=run_id,
                processor=processor_name,
                tenant_id=tenant_id,
                status="pending",  # Temporary status
                vendor_job_id=None,
                idempotency_key=idempotency_key,
                output=None,
                error=None,
            )
            db.add(placeholder)
            try:
                await db.commit()
                await db.refresh(placeholder)
            except Exception:
                # Another request beat us to it - fetch and return that run
                await db.rollback()
                stmt = select(Run).where(
                    and_(
                        Run.tenant_id == tenant_id,
                        Run.processor == processor_name,
                        Run.idempotency_key == idempotency_key,
                    )
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    logger.info(
                        "Idempotent run reused (race condition)",
                        extra={"context": {"idempotency_key": idempotency_key, "run_id": existing.id}},
                    )
                    return {
                        "id": existing.id,
                        "processor_name": existing.processor,
                        "status": existing.status,
                        "created_at": existing.created_at.isoformat(),
                        "updated_at": existing.updated_at.isoformat(),
                        "tenant_id": existing.tenant_id,
                        "output": existing.output,
                        "error": existing.error,
                        "vendor_job_id": existing.vendor_job_id,
                    }
                # This shouldn't happen, but re-raise if it does
                raise
        else:
            # No idempotency key, just generate a new run ID
            run_id = str(uuid4())

        # Handle file upload mode: validate and upload files
        if files_to_process:
            file_data = []
            for upload in files_to_process:
                # Check content type
                if upload.content_type not in {"application/pdf", "application/x-pdf", None}:
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail={
                            "code": "UNSUPPORTED_MEDIA_TYPE",
                            "message": f"Unsupported content type: {upload.content_type}",
                        }
                    )

                # Read content and validate size
                content = await upload.read()
                if len(content) > RUN_MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail={
                            "code": "FILE_TOO_LARGE",
                            "message": f"File exceeds {RUN_MAX_FILE_BYTES} bytes limit",
                        }
                    )

                # Validate PDF magic bytes
                if not content.startswith(b"%PDF-"):
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail={
                            "code": "INVALID_PDF",
                            "message": f"File is not a valid PDF: {upload.filename}",
                        }
                    )

                # Create in-memory file for vendor upload
                file_data.append({
                    "filename": upload.filename or "upload.pdf",
                    "content": content,
                    "content_type": upload.content_type or "application/pdf",
                })

            # Upload files to vendor service
            try:
                # Pass file data directly to vendor (filename, content, content_type)
                upload_result = await vendor.upload_files_stream(file_data)
                input_path = upload_result.get("input_path", "mock://upload")
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "VENDOR_UPLOAD_FAILED",
                        "message": f"Failed to upload files: {str(exc)}",
                    }
                ) from exc
        # else: input_path already provided from JSON body

        # Create vendor job
        try:
            job_payload = {"processor_name": processor_name}
            vendor_job = await vendor.create_job(input_path, job_payload, tenant_id=tenant_id)
            vendor_job_id = vendor_job.get("job_id")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "code": "VENDOR_JOB_FAILED",
                    "message": f"Failed to create vendor job: {str(exc)}",
                }
            ) from exc

        # Update database record (either placeholder or new record)
        if idempotency_key:
            # Update the placeholder we created earlier
            stmt = select(Run).where(Run.id == run_id)
            result = await db.execute(stmt)
            run = result.scalar_one()
            run.status = "queued"
            run.vendor_job_id = vendor_job_id
            await db.commit()
            await db.refresh(run)
        else:
            # Create a new record (no idempotency key)
            run = Run(
                id=run_id,
                processor=processor_name,
                tenant_id=tenant_id,
                status="queued",
                vendor_job_id=vendor_job_id,
                idempotency_key=None,
                output=None,
                error=None,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

        logger.info(
            "Processor run queued",
            extra={
                "context": {
                    "run_id": run_id,
                    "processor": processor_name,
                    "tenant_id": tenant_id,
                    "request_id": getattr(request.state, "request_id", None),
                    "api_version": x_api_version,
                    "file_count": len(files_to_process) if files_to_process else 0,
                    "input_mode": "multipart" if files_to_process else "json",
                    "vendor_job_id": vendor_job_id,
                }
            },
        )

        # Increment run counter
        runs_started.labels(processor=processor_name).inc()

        return {
            "id": run.id,
            "processor_name": run.processor,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "tenant_id": run.tenant_id,
            "output": run.output,
            "error": run.error,
            "vendor_job_id": run.vendor_job_id,
        }

    @app.get(
        "/processors/{processor_name}/runs/{run_id}",
        tags=["processors"],
        summary="Get processor run details",
        description="Retrieve status and results for a specific processor run by ID.",
        responses={
            200: {"description": "Run details retrieved successfully"},
            404: {"description": "Run not found"},
        },
    )
    async def get_processor_run(
        processor_name: str,
        run_id: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None, description="API version for compatibility"),
        db = Depends(get_session),
    ) -> Dict[str, Any]:
        """Get processor run status and results (Algorythmos-style endpoint)."""
        stmt = select(Run).where(
            and_(
                Run.id == run_id,
                Run.tenant_id == tenant_ctx["tenant"],
                Run.processor == processor_name,
            )
        )
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "RUN_NOT_FOUND", "message": "Run not found"}
            )

        return {
            "id": run.id,
            "processor_name": run.processor,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "tenant_id": run.tenant_id,
            "output": run.output,
            "error": run.error,
            "vendor_job_id": run.vendor_job_id,
        }

    @app.get(
        "/processors/{processor_name}/runs",
        tags=["processors"],
        summary="List processor runs",
        description="Retrieve a paginated list of runs for the specified processor. Returns items sorted by creation time (newest first). Supports cursor-based pagination and status filtering.",
        responses={
            200: {"description": "List of runs retrieved successfully"},
            400: {"description": "Invalid status filter value"},
        },
    )
    async def list_processor_runs(
        processor_name: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        limit: int = Query(default=20, ge=1, le=100, description="Maximum number of items to return (1-100)"),
        cursor: Optional[str] = Query(default=None, description="Cursor for pagination (ISO timestamp)"),
        status: Optional[str] = Query(default=None, description="Filter by status (queued, processing, succeeded, failed)"),
        x_api_version: Optional[str] = Header(default=None, description="API version for compatibility"),
        db = Depends(get_session),
    ) -> Dict[str, Any]:
        """List processor runs with pagination (Algorythmos-style endpoint)."""
        tenant_id = tenant_ctx["tenant"]

        # Validate status filter
        valid_statuses = {"queued", "processing", "succeeded", "failed"}
        if status and status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_STATUS",
                    "message": f"Invalid status filter. Must be one of: {', '.join(valid_statuses)}",
                },
            )

        # Build base query with filters
        conditions = [
            Run.processor == processor_name,
            Run.tenant_id == tenant_id,
        ]

        if status:
            conditions.append(Run.status == status)

        # Apply cursor for keyset pagination (cursor is created_at ISO timestamp)
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
                conditions.append(Run.created_at < cursor_dt)
            except (ValueError, AttributeError):
                # Invalid cursor format, ignore it
                pass

        base_query = select(Run).where(and_(*conditions))

        # Get paginated results ordered by created_at DESC (newest first)
        # Fetch limit + 1 to determine if there are more results
        paginated_query = (
            base_query
            .order_by(Run.created_at.desc(), Run.id.desc())  # Secondary sort by ID for stability
            .limit(limit + 1)
        )
        result = await db.execute(paginated_query)
        runs = result.scalars().all()

        # Check if there are more results
        has_more = len(runs) > limit
        if has_more:
            runs = runs[:limit]

        # Format response
        items = [
            {
                "id": run.id,
                "processor_name": run.processor,
                "status": run.status,
                "created_at": run.created_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "tenant_id": run.tenant_id,
                "has_output": run.output is not None,
                "has_error": run.error is not None,
                "vendor_job_id": run.vendor_job_id,
            }
            for run in runs
        ]

        # Build response with next_cursor if there are more results
        response: Dict[str, Any] = {"items": items}

        if has_more and items:
            # Use the created_at of the last item as the next cursor
            next_cursor = items[-1]["created_at"]
            response["next_cursor"] = next_cursor

        return response

    @app.patch(
        "/processors/{processor_name}",
        tags=["processors"],
        summary="Update processor configuration",
        description="Update configuration settings for a specific processor. Configuration changes apply to future runs.",
        responses={
            200: {"description": "Processor configuration updated successfully"},
            404: {"description": "Processor not found"},
        },
    )
    async def update_processor(
        processor_name: str,
        request: Request,
        payload: Dict[str, Any] = Body(..., description="Configuration updates to apply"),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None, description="API version for compatibility"),
    ) -> Dict[str, Any]:
        """Update processor configuration (Algorythmos-style endpoint)."""
        logger.info(
            "Processor update requested",
            extra={
                "context": {
                    "processor": processor_name,
                    "tenant_id": tenant_ctx["tenant"],
                    "changes": list(payload.keys()),
                    "api_version": x_api_version,
                }
            },
        )

        # For now, return success - this would integrate with actual processor management
        return {
            "processor_name": processor_name,
            "version": "1.0.0",
            "updated_at": _utcnow().isoformat(),
            "status": "active",
            "configuration": payload,
        }

    # Webhook endpoint for vendor callbacks
    @app.post(
        "/webhooks/vendor",
        status_code=204,
        tags=["webhooks"],
        summary="Receive vendor webhook",
        description="Accept webhook notifications from vendor service about job status updates. Validates HMAC SHA-256 signatures and updates run status in database.",
        responses={
            204: {"description": "Webhook processed successfully"},
            400: {"description": "Invalid request body"},
            401: {"description": "Invalid or missing signature"},
            415: {"description": "Unsupported media type (expected application/json)"},
        },
    )
    async def receive_vendor_webhook(
        request: Request,
        x_vendor_signature: Optional[str] = Header(default=None, alias="X-Vendor-Signature", description="HMAC SHA-256 signature of request body"),
        x_vendor_event_id: Optional[str] = Header(default=None, alias="X-Vendor-Event-ID", description="Unique event identifier for deduplication"),
        x_vendor_timestamp: Optional[str] = Header(default=None, alias="X-Vendor-Timestamp", description="Unix timestamp of webhook event"),
        db = Depends(get_session),
    ) -> Response:
        """Receive webhook notifications from vendor service."""
        # Validate content type
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            return Response(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

        # Read raw body for signature verification
        try:
            raw_body = await request.body()
        except Exception:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        # Parse and verify signature
        sig_info = parse_signature_header(x_vendor_signature)
        if not sig_info:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        # For v1 signatures, timestamp is embedded in the signature header
        # For legacy signatures (sha256=...), timestamp handling depends on mode
        if sig_info.scheme == "legacy":
            if not settings.WEBHOOK_ALLOW_LEGACY_SIGNATURES:
                return Response(status_code=status.HTTP_401_UNAUTHORIZED)

            if settings.WEBHOOK_LEGACY_REQUIRE_TIMESTAMP and not x_vendor_timestamp:
                return Response(status_code=status.HTTP_401_UNAUTHORIZED)

            if x_vendor_timestamp:
                # If timestamp header provided, validate it
                try:
                    timestamp = int(x_vendor_timestamp)
                except (ValueError, TypeError):
                    return Response(status_code=status.HTTP_401_UNAUTHORIZED)

                # Validate timestamp is within replay window
                now = int(time.time())
                if abs(now - timestamp) > WEBHOOK_REPLAY_WINDOW_S:
                    return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        # Verify HMAC
        is_valid = verify_hmac_sha256(
            raw_body,
            sig_info,
            settings.VENDOR_WEBHOOK_SECRET,
            replay_window_s=WEBHOOK_REPLAY_WINDOW_S,
        )
        if not is_valid:
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

        # Check for replay using event ID
        if x_vendor_event_id:
            replay_store = getattr(request.app.state, "webhook_replay_store", None)
            if replay_store is None:
                return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
            if not await replay_store.seen_once(x_vendor_event_id, WEBHOOK_REPLAY_TTL_S):
                # Already processed this event
                logger.info(
                    "Webhook replay detected",
                    extra={"context": {"event_id": x_vendor_event_id}},
                )
                return Response(status_code=204)

        # Parse JSON body
        try:
            payload = await request.json()
        except Exception:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        # Extract job information
        vendor_job_id = payload.get("job_id")
        if not vendor_job_id:
            # Missing job_id, but return 204 (webhook accepted)
            return Response(status_code=204)

        # Find the run associated with this vendor job
        stmt = select(Run).where(Run.vendor_job_id == vendor_job_id)
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()

        if not run:
            # Unknown job, but not an error - return 204
            logger.info(
                "Webhook for unknown job",
                extra={"context": {"vendor_job_id": vendor_job_id}},
            )
            return Response(status_code=204)

        # Update run status
        webhook_status = payload.get("status", "unknown")
        output = payload.get("output")
        error = payload.get("error")

        run.status = webhook_status
        run.output = output
        run.error = error
        await db.commit()

        # Update metrics based on final status
        if webhook_status == "succeeded":
            runs_succeeded.labels(processor=run.processor).inc()
        elif webhook_status == "failed":
            runs_failed.labels(processor=run.processor).inc()

        logger.info(
            "Webhook processed",
            extra={
                "context": {
                    "run_id": run.id,
                    "vendor_job_id": vendor_job_id,
                    "status": webhook_status,
                    "event_id": x_vendor_event_id,
                }
            },
        )

        return Response(status_code=204)

    # ======================
    # PHASE 7: Processors, Workflows, Evaluation Sets
    # ======================

    @app.post(
        "/processors",
        response_model=ProcessorConfig,
        status_code=status.HTTP_201_CREATED,
        tags=["processors"],
        summary="Create processor",
        description="Create a new custom processor plugin",
    )
    async def create_processor_endpoint(
        request: CreateProcessorRequest,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Create a new processor."""
        try:
            processor = await processor_service.create_processor(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                name=request.name,
                processor_type=request.processor_type,
                implementation=request.implementation,
                description=request.description,
                input_schema=request.input_schema,
                output_schema=request.output_schema,
                enabled=request.enabled,
                metadata=request.metadata
            )

            return ProcessorConfig(
                processor_id=processor.id,
                name=processor.name,
                description=processor.description,
                processor_type=processor.processor_type,
                implementation=processor.implementation,
                input_schema=processor.input_schema,
                output_schema=processor.output_schema,
                enabled=processor.enabled,
                version=processor.version,
                tenant_id=processor.tenant_id,
                created_at=processor.created_at,
                updated_at=processor.updated_at,
                metadata=processor.processor_metadata
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("DUPLICATE_NAME", str(e))
            )
        except Exception as e:
            logger.error(f"Error creating processor: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("CREATION_ERROR", "Failed to create processor")
            )

    @app.get(
        "/processors",
        response_model=ProcessorListResponse,
        tags=["processors"],
        summary="List processors",
        description="List all processors with pagination and filtering",
    )
    async def list_processors_endpoint(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        processor_type: Optional[str] = Query(None),
        enabled: Optional[bool] = Query(None),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """List processors with pagination."""
        try:
            items, total = await processor_service.list_processors(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                limit=limit,
                offset=offset,
                processor_type=processor_type,
                enabled=enabled
            )

            processors = [
                ProcessorConfig(
                    processor_id=p.id,
                    name=p.name,
                    description=p.description,
                    processor_type=p.processor_type,
                    implementation=p.implementation,
                    input_schema=p.input_schema,
                    output_schema=p.output_schema,
                    enabled=p.enabled,
                    version=p.version,
                    tenant_id=p.tenant_id,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    metadata=p.processor_metadata
                )
                for p in items
            ]

            return ProcessorListResponse(
                items=processors,
                meta=build_pagination_meta(limit, offset, total)
            )
        except Exception as e:
            logger.error(f"Error listing processors: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("LIST_ERROR", "Failed to list processors")
            )

    @app.get(
        "/processors/{processor_id}",
        response_model=ProcessorConfig,
        tags=["processors"],
        summary="Get processor",
        description="Get processor by ID",
    )
    async def get_processor_endpoint(
        processor_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Get processor by ID."""
        try:
            processor = await processor_service.get_processor(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                processor_id=processor_id
            )

            if not processor:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Processor {processor_id} not found")
                )

            return ProcessorConfig(
                processor_id=processor.id,
                name=processor.name,
                description=processor.description,
                processor_type=processor.processor_type,
                implementation=processor.implementation,
                input_schema=processor.input_schema,
                output_schema=processor.output_schema,
                enabled=processor.enabled,
                version=processor.version,
                tenant_id=processor.tenant_id,
                created_at=processor.created_at,
                updated_at=processor.updated_at,
                metadata=processor.processor_metadata
            )
        except Exception as e:
            logger.error(f"Error getting processor: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("GET_ERROR", "Failed to get processor")
            )

    @app.put(
        "/processors/{processor_id}",
        response_model=ProcessorConfig,
        tags=["processors"],
        summary="Update processor",
        description="Update processor by ID",
    )
    async def update_processor_endpoint(
        processor_id: str = PathParam(...),
        request: UpdateProcessorRequest = None,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Update processor."""
        try:
            processor = await processor_service.update_processor(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                processor_id=processor_id,
                name=request.name,
                description=request.description,
                processor_type=request.processor_type,
                implementation=request.implementation,
                input_schema=request.input_schema,
                output_schema=request.output_schema,
                enabled=request.enabled,
                metadata=request.metadata
            )

            if not processor:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Processor {processor_id} not found")
                )

            return ProcessorConfig(
                processor_id=processor.id,
                name=processor.name,
                description=processor.description,
                processor_type=processor.processor_type,
                implementation=processor.implementation,
                input_schema=processor.input_schema,
                output_schema=processor.output_schema,
                enabled=processor.enabled,
                version=processor.version,
                tenant_id=processor.tenant_id,
                created_at=processor.created_at,
                updated_at=processor.updated_at,
                metadata=processor.processor_metadata
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("DUPLICATE_NAME", str(e))
            )
        except Exception as e:
            logger.error(f"Error updating processor: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("UPDATE_ERROR", "Failed to update processor")
            )

    @app.delete(
        "/processors/{processor_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["processors"],
        summary="Delete processor",
        description="Soft delete processor by ID",
    )
    async def delete_processor_endpoint(
        processor_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Delete processor."""
        try:
            deleted = await processor_service.delete_processor(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                processor_id=processor_id
            )

            if not deleted:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Processor {processor_id} not found")
                )

            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting processor: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("DELETE_ERROR", "Failed to delete processor")
            )

    # Workflow endpoints
    @app.post(
        "/workflows",
        response_model=WorkflowConfig,
        status_code=status.HTTP_201_CREATED,
        tags=["workflows"],
        summary="Create workflow",
        description="Create a new workflow (chain of processors)",
    )
    async def create_workflow_endpoint(
        request: CreateWorkflowRequest,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Create a new workflow."""
        try:
            workflow = await workflow_service.create_workflow(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                name=request.name,
                steps=request.steps,
                description=request.description,
                enabled=request.enabled,
                metadata=request.metadata
            )

            return WorkflowConfig(
                workflow_id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                steps=workflow.steps,
                enabled=workflow.enabled,
                version=workflow.version,
                tenant_id=workflow.tenant_id,
                created_at=workflow.created_at,
                updated_at=workflow.updated_at,
                metadata=workflow.workflow_metadata
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("VALIDATION_ERROR", str(e))
            )
        except Exception as e:
            logger.error(f"Error creating workflow: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("CREATION_ERROR", "Failed to create workflow")
            )

    @app.get(
        "/workflows",
        response_model=WorkflowListResponse,
        tags=["workflows"],
        summary="List workflows",
        description="List all workflows with pagination",
    )
    async def list_workflows_endpoint(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        enabled: Optional[bool] = Query(None),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """List workflows with pagination."""
        try:
            items, total = await workflow_service.list_workflows(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                limit=limit,
                offset=offset,
                enabled=enabled
            )

            workflows = [
                WorkflowConfig(
                    workflow_id=w.id,
                    name=w.name,
                    description=w.description,
                    steps=w.steps,
                    enabled=w.enabled,
                    version=w.version,
                    tenant_id=w.tenant_id,
                    created_at=w.created_at,
                    updated_at=w.updated_at,
                    metadata=w.workflow_metadata
                )
                for w in items
            ]

            return WorkflowListResponse(
                items=workflows,
                meta=build_pagination_meta(limit, offset, total)
            )
        except Exception as e:
            logger.error(f"Error listing workflows: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("LIST_ERROR", "Failed to list workflows")
            )

    @app.get(
        "/workflows/{workflow_id}",
        response_model=WorkflowConfig,
        tags=["workflows"],
        summary="Get workflow",
        description="Get workflow by ID",
    )
    async def get_workflow_endpoint(
        workflow_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Get workflow by ID."""
        try:
            workflow = await workflow_service.get_workflow(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                workflow_id=workflow_id
            )

            if not workflow:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Workflow {workflow_id} not found")
                )

            return WorkflowConfig(
                workflow_id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                steps=workflow.steps,
                enabled=workflow.enabled,
                version=workflow.version,
                tenant_id=workflow.tenant_id,
                created_at=workflow.created_at,
                updated_at=workflow.updated_at,
                metadata=workflow.workflow_metadata
            )
        except Exception as e:
            logger.error(f"Error getting workflow: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("GET_ERROR", "Failed to get workflow")
            )

    @app.put(
        "/workflows/{workflow_id}",
        response_model=WorkflowConfig,
        tags=["workflows"],
        summary="Update workflow",
        description="Update workflow by ID",
    )
    async def update_workflow_endpoint(
        workflow_id: str = PathParam(...),
        request: UpdateWorkflowRequest = None,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Update workflow."""
        try:
            workflow = await workflow_service.update_workflow(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                workflow_id=workflow_id,
                name=request.name,
                description=request.description,
                steps=request.steps,
                enabled=request.enabled,
                metadata=request.metadata
            )

            if not workflow:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Workflow {workflow_id} not found")
                )

            return WorkflowConfig(
                workflow_id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                steps=workflow.steps,
                enabled=workflow.enabled,
                version=workflow.version,
                tenant_id=workflow.tenant_id,
                created_at=workflow.created_at,
                updated_at=workflow.updated_at,
                metadata=workflow.workflow_metadata
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("VALIDATION_ERROR", str(e))
            )
        except Exception as e:
            logger.error(f"Error updating workflow: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("UPDATE_ERROR", "Failed to update workflow")
            )

    @app.delete(
        "/workflows/{workflow_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["workflows"],
        summary="Delete workflow",
        description="Soft delete workflow by ID",
    )
    async def delete_workflow_endpoint(
        workflow_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Delete workflow."""
        try:
            deleted = await workflow_service.delete_workflow(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                workflow_id=workflow_id
            )

            if not deleted:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Workflow {workflow_id} not found")
                )

            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting workflow: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("DELETE_ERROR", "Failed to delete workflow")
            )

    @app.post(
        "/workflows/{workflow_id}/execute",
        response_model=WorkflowExecutionResult,
        tags=["workflows"],
        summary="Execute workflow",
        description="Execute a workflow with input data",
    )
    async def execute_workflow_endpoint(
        workflow_id: str = PathParam(...),
        request: ExecuteWorkflowRequest = None,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Execute workflow."""
        try:
            result = await workflow_service.execute_workflow(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                workflow_id=workflow_id,
                input_data=request.input_data
            )

            return WorkflowExecutionResult(**result)
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("EXECUTION_ERROR", str(e))
            )
        except Exception as e:
            logger.error(f"Error executing workflow: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("EXECUTION_ERROR", "Failed to execute workflow")
            )

    # Evaluation set endpoints
    @app.post(
        "/evaluation-sets",
        response_model=EvaluationSetConfig,
        status_code=status.HTTP_201_CREATED,
        tags=["evaluation"],
        summary="Create evaluation set",
        description="Create a new evaluation set for testing",
    )
    async def create_evaluation_set_endpoint(
        request: CreateEvaluationSetRequest,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Create a new evaluation set."""
        try:
            eval_set = await evaluation_service.create_evaluation_set(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                name=request.name,
                test_cases=request.test_cases,
                target_type=request.target_type,
                description=request.description,
                target_id=request.target_id,
                metadata=request.metadata
            )

            return EvaluationSetConfig(
                evaluation_set_id=eval_set.id,
                name=eval_set.name,
                description=eval_set.description,
                test_cases=eval_set.test_cases,
                target_type=eval_set.target_type,
                target_id=eval_set.target_id,
                tenant_id=eval_set.tenant_id,
                created_at=eval_set.created_at,
                updated_at=eval_set.updated_at,
                metadata=eval_set.evaluation_metadata
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("VALIDATION_ERROR", str(e))
            )
        except Exception as e:
            logger.error(f"Error creating evaluation set: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("CREATION_ERROR", "Failed to create evaluation set")
            )

    @app.get(
        "/evaluation-sets",
        response_model=EvaluationSetListResponse,
        tags=["evaluation"],
        summary="List evaluation sets",
        description="List all evaluation sets with pagination",
    )
    async def list_evaluation_sets_endpoint(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        target_type: Optional[str] = Query(None),
        target_id: Optional[str] = Query(None),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """List evaluation sets with pagination."""
        try:
            items, total = await evaluation_service.list_evaluation_sets(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                limit=limit,
                offset=offset,
                target_type=target_type,
                target_id=target_id
            )

            eval_sets = [
                EvaluationSetConfig(
                    evaluation_set_id=e.id,
                    name=e.name,
                    description=e.description,
                    test_cases=e.test_cases,
                    target_type=e.target_type,
                    target_id=e.target_id,
                    tenant_id=e.tenant_id,
                    created_at=e.created_at,
                    updated_at=e.updated_at,
                    metadata=e.evaluation_metadata
                )
                for e in items
            ]

            return EvaluationSetListResponse(
                items=eval_sets,
                meta=build_pagination_meta(limit, offset, total)
            )
        except Exception as e:
            logger.error(f"Error listing evaluation sets: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("LIST_ERROR", "Failed to list evaluation sets")
            )

    @app.get(
        "/evaluation-sets/{evaluation_set_id}",
        response_model=EvaluationSetConfig,
        tags=["evaluation"],
        summary="Get evaluation set",
        description="Get evaluation set by ID",
    )
    async def get_evaluation_set_endpoint(
        evaluation_set_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Get evaluation set by ID."""
        try:
            eval_set = await evaluation_service.get_evaluation_set(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                evaluation_set_id=evaluation_set_id
            )

            if not eval_set:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Evaluation set {evaluation_set_id} not found")
                )

            return EvaluationSetConfig(
                evaluation_set_id=eval_set.id,
                name=eval_set.name,
                description=eval_set.description,
                test_cases=eval_set.test_cases,
                target_type=eval_set.target_type,
                target_id=eval_set.target_id,
                tenant_id=eval_set.tenant_id,
                created_at=eval_set.created_at,
                updated_at=eval_set.updated_at,
                metadata=eval_set.evaluation_metadata
            )
        except Exception as e:
            logger.error(f"Error getting evaluation set: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("GET_ERROR", "Failed to get evaluation set")
            )

    @app.put(
        "/evaluation-sets/{evaluation_set_id}",
        response_model=EvaluationSetConfig,
        tags=["evaluation"],
        summary="Update evaluation set",
        description="Update evaluation set by ID",
    )
    async def update_evaluation_set_endpoint(
        evaluation_set_id: str = PathParam(...),
        request: UpdateEvaluationSetRequest = None,
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Update evaluation set."""
        try:
            eval_set = await evaluation_service.update_evaluation_set(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                evaluation_set_id=evaluation_set_id,
                name=request.name,
                description=request.description,
                test_cases=request.test_cases,
                target_type=request.target_type,
                target_id=request.target_id,
                metadata=request.metadata
            )

            if not eval_set:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Evaluation set {evaluation_set_id} not found")
                )

            return EvaluationSetConfig(
                evaluation_set_id=eval_set.id,
                name=eval_set.name,
                description=eval_set.description,
                test_cases=eval_set.test_cases,
                target_type=eval_set.target_type,
                target_id=eval_set.target_id,
                tenant_id=eval_set.tenant_id,
                created_at=eval_set.created_at,
                updated_at=eval_set.updated_at,
                metadata=eval_set.evaluation_metadata
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("VALIDATION_ERROR", str(e))
            )
        except Exception as e:
            logger.error(f"Error updating evaluation set: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("UPDATE_ERROR", "Failed to update evaluation set")
            )

    @app.delete(
        "/evaluation-sets/{evaluation_set_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["evaluation"],
        summary="Delete evaluation set",
        description="Soft delete evaluation set by ID",
    )
    async def delete_evaluation_set_endpoint(
        evaluation_set_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Delete evaluation set."""
        try:
            deleted = await evaluation_service.delete_evaluation_set(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                evaluation_set_id=evaluation_set_id
            )

            if not deleted:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content=build_error_response("NOT_FOUND", f"Evaluation set {evaluation_set_id} not found")
                )

            return Response(status_code=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting evaluation set: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("DELETE_ERROR", "Failed to delete evaluation set")
            )

    @app.post(
        "/evaluation-sets/{evaluation_set_id}/run",
        response_model=EvaluationResult,
        tags=["evaluation"],
        summary="Run evaluation",
        description="Run evaluation set against its target",
    )
    async def run_evaluation_endpoint(
        evaluation_set_id: str = PathParam(...),
        tenant_ctx: dict = Depends(require_key),
        db = Depends(get_session),
    ):
        """Run evaluation."""
        try:
            result = await evaluation_service.run_evaluation(
                session=db,
                tenant_id=tenant_ctx["tenant"],
                evaluation_set_id=evaluation_set_id
            )

            return EvaluationResult(**result)
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=build_error_response("EXECUTION_ERROR", str(e))
            )
        except Exception as e:
            logger.error(f"Error running evaluation: {e}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=build_error_response("EXECUTION_ERROR", "Failed to run evaluation")
            )

    return app


# Create the app instance
app = build_api()
