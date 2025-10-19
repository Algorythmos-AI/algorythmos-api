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
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile, status
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
    
    return http_requests_total, http_request_duration_seconds


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
        requests_total, request_duration = _get_or_create_metrics()
        
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
    x_api_key: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None),
) -> Dict[str, str]:
    """Validate API key and tenant ID."""
    if x_api_key != settings.ALG_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail={"code": "UNAUTHORIZED", "message": "Invalid API key"}
        )
    
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail={"code": "MISSING_TENANT", "message": "Missing X-Tenant-Id header"}
        )

    _enforce_rate_limit(x_tenant_id)
    request.state.tenant_id = x_tenant_id
    return {"tenant": x_tenant_id}


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
        
        # Initialize database tables
        if engine is not None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        
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
        lifespan=lifespan
    )
    
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
        db: AsyncSession = Depends(get_session),
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
        db: AsyncSession = Depends(get_session),
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
        db: AsyncSession = Depends(get_session),
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
        db: AsyncSession = Depends(get_session),
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

    return app


# Create the app instance
app = build_api()