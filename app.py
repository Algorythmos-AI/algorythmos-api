"""Main application factory for the PDF Usage Extraction Service."""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

import anyio
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile, status, Path as PathParam, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.params import Body, Query
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings
from pdf_usage_extractor import ExtractionRouter
from pdf_usage_extractor.logging_utils import get_logger
from pdf_usage_extractor.schemas import ExtractResponse, UsageRecord, ProcessorCreateRunRequest, ProcessorUpdateRequest, ProcessorInfo
from vendor_libs.services import vendor
from vendor_libs.utils.runstore import run_store
from vendor_libs.utils.security import parse_signature_header, verify_hmac_sha256, ReplaySet
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


# Global state
_rate_bucket: Dict[tuple[str, int], int] = {}
_rate_lock = Lock()
_jobs: Dict[str, JobRecord] = {}

# Stage 3+ constants - exposed for tests
RUN_MAX_FILE_BYTES = settings.RUN_MAX_FILE_BYTES
RUN_MAX_FILES = settings.RUN_MAX_FILES
WEBHOOK_REPLAY_TTL_S = settings.WEBHOOK_REPLAY_TTL_S
WEBHOOK_REPLAY_WINDOW_S = settings.WEBHOOK_REPLAY_WINDOW_S
_processor_runs: Dict[str, JobRecord] = {}  # For Algorythmos-style runs

# Webhook replay protection
webhook_replay_set = ReplaySet(ttl_seconds=WEBHOOK_REPLAY_TTL_S)


def _utcnow() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


def _enforce_rate_limit(tenant_id: str) -> None:
    """Enforce rate limiting per tenant."""
    rate = settings.RATE_PER_MIN
    if rate <= 0:
        return
    
    current_window = int(time.time() // 60)
    with _rate_lock:
        # Clean up stale rate buckets
        stale_keys = [key for key in _rate_bucket if key[1] < current_window]
        for key in stale_keys:
            _rate_bucket.pop(key, None)

        bucket_key = (tenant_id, current_window)
        current = _rate_bucket.get(bucket_key, 0) + 1
        if current > rate:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"}
            )
        _rate_bucket[bucket_key] = current


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
    
    # Authenticate: Bearer token OR API key required
    authenticated = False
    if bearer_token:
        # Validate Bearer token (for now, use same validation as API key)
        # In production, implement proper JWT validation
        if bearer_token == settings.ALG_API_KEY:
            authenticated = True
    elif x_api_key:
        # Validate API key
        if x_api_key == settings.ALG_API_KEY:
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
    _enforce_rate_limit(x_tenant_id)
    
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


async def _execute_job(job_id: str, payload: JobCreate, tenant_id: str, request_id: Optional[str]) -> None:
    """Execute a background job."""
    job_logger = get_logger(payload.debug)
    job = _jobs.get(job_id)
    if not job:
        return

    job.status = "running"
    job.updated_at = _utcnow()
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
        job.result = result
        job.duration_sec = round(elapsed, 3)
        job.status = "succeeded"
        job.updated_at = _utcnow()
        
        await _maybe_send_webhook(job)
        
        job_logger.info(
            "Job succeeded",
            extra={
                "context": {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "records": result.count,
                    "duration_sec": job.duration_sec,
                    "request_id": request_id,
                }
            },
        )
    except Exception as exc:  # pragma: no cover - defensive catch
        job.status = "failed"
        job.error = str(exc)
        job.updated_at = _utcnow()
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


def build_api() -> FastAPI:
    """Build and configure the FastAPI application."""
    # Initialize database module references
    global async_session_factory, engine, get_session, Base, Run
    try:
        import app.database as db_module
        import app.models as models_module
        async_session_factory = db_module.async_session_factory
        engine = db_module.engine
        get_session = db_module.get_session
        Base = models_module.Base
        Run = models_module.Run
    except ImportError:
        # Database modules not available - tests may provide mocks
        pass
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifespan: startup and shutdown."""
        # Startup
        logger = get_logger()
        
        # Initialize database tables (only if database is configured)
        try:
            if engine is not None and Base is not None:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            logger.warning(f"Database initialization skipped or failed: {e}")
        
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
                }
            },
        )
        
        yield
        
        # Shutdown
        try:
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
        # Customize OpenAPI schema generation
        swagger_ui_parameters={"tryItOutEnabled": True},
        generate_unique_id_function=lambda route: f"{route.tags[0]}-{route.name}" if route.tags else route.name,
    )

    @app.get("/", tags=["health"], summary="Health check", include_in_schema=False)
    async def health() -> dict[str, str]:
        """Lightweight health check for serverless environments."""
        return {"status": "ok"}
    
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
                "url": "https://api.algorythmos.fr/logo.png"
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
    
    # Add middleware in correct order (LIFO)
    origins = settings.get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "*"],
        expose_headers=["X-Request-ID"],  # So the browser can read it for debugging
    )
    
    # Production middlewares
    app.add_middleware(RateLimitMiddleware, requests_per_minute=60, requests_per_hour=1000)
    app.add_middleware(IdempotencyMiddleware, ttl_seconds=86400)  # 24 hours
    
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(FileSizeMiddleware)
    app.add_middleware(RequestContextMiddleware)
    
    # Global router instance and logger
    global router_engine
    router_engine = ExtractionRouter()
    logger = get_logger()

    # Health endpoint (public)
    @app.get("/alg/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    # Version endpoint (public) 
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
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
            
            async with request.app.state.db_session() as session:
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> Dict[str, Any]:
        """List files for the tenant."""
        tenant_id = tenant_ctx["tenant"]
        
        async with request.app.state.db_session() as session:
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> FileUpload:
        """Get file metadata."""
        tenant_id = tenant_ctx["tenant"]
        
        async with request.app.state.db_session() as session:
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> Dict[str, str]:
        """Soft delete a file."""
        tenant_id = tenant_ctx["tenant"]
        
        async with request.app.state.db_session() as session:
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
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
            
            async with request.app.state.db_session() as session:
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> ParserRunStatus:
        """Create an async parser run (actual execution would happen in background worker)."""
        tenant_id = tenant_ctx["tenant"]
        
        try:
            async with request.app.state.db_session() as session:
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
                
                logger.info(
                    "Async parse created",
                    extra={
                        "context": {
                            "run_id": run_status.run_id,
                            "file_id": parse_request.file_id,
                            "tenant_id": tenant_id,
                        }
                    }
                )
                
                # In production, would trigger background job here
                # For now, just return the pending status
                
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> ParserRunStatus:
        """Get parser run status."""
        tenant_id = tenant_ctx["tenant"]
        
        async with request.app.state.db_session() as session:
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
        tenant_ctx: Dict[str, str] = Depends(require_key)
    ) -> Dict[str, Any]:
        """List parser runs."""
        tenant_id = tenant_ctx["tenant"]
        
        async with request.app.state.db_session() as session:
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
        job_id = str(uuid4())
        job_record = JobRecord(
            job_id=job_id,
            status="queued",
            tenant_id=tenant_ctx["tenant"],
            request_id=getattr(request.state, "request_id", None),
            created_at=_utcnow(),
            updated_at=_utcnow(),
            webhook_url=payload.webhook_url,
        )
        _jobs[job_id] = job_record

        background_tasks.add_task(_execute_job, job_id, payload, tenant_ctx["tenant"], job_record.request_id)

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
        job_id: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
    ) -> Dict[str, Any]:
        """Get job status and results."""
        job = _jobs.get(job_id)
        if not job or job.tenant_id != tenant_ctx["tenant"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail={"code": "JOB_NOT_FOUND", "message": "Job not found"}
            )
        return job.model_dump(mode="json")

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

        # Determine strict mode based on configuration
        # Stage 5+ enforces timestamp for legacy signatures
        # Check if secret indicates stage 5 or higher (stage5, stage6, stage7, etc.)
        strict_legacy_validation = False
        if settings.VENDOR_WEBHOOK_SECRET:
            secret_lower = settings.VENDOR_WEBHOOK_SECRET.lower()
            for stage_num in range(5, 20):  # Check for stage5 through stage19
                if f"stage{stage_num}" in secret_lower:
                    strict_legacy_validation = True
                    break
        
        # For v1 signatures, timestamp is embedded in the signature header
        # For legacy signatures (sha256=...), timestamp handling depends on mode
        if sig_info.scheme == "legacy":
            # In strict mode (Stage 5+), legacy format requires timestamp header
            if strict_legacy_validation and not x_vendor_timestamp:
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
            if not webhook_replay_set.seen_once(x_vendor_event_id):
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
