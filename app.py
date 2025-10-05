"""Main application factory for the PDF Usage Extraction Service."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Literal, Optional, Sequence
from uuid import uuid4

APP_PACKAGE_PATH = Path(__file__).resolve().parent / "app"
__path__ = [str(APP_PACKAGE_PATH)]  # type: ignore[name-defined]
if '__spec__' in globals() and __spec__ is not None:
    __spec__.submodule_search_locations = __path__  # type: ignore[attr-defined]

import anyio
import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.params import Body, Query
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from pdf_usage_extractor import ExtractionRouter
from pdf_usage_extractor.logging_utils import get_logger
from pdf_usage_extractor.schemas import (
    ExtractResponse,
    UsageRecord,
    ProcessorCreateRunRequest,
    ProcessorUpdateRequest,
    ProcessorInfo,
)
from vendor_libs.services import vendor as vendor_services
from vendor_libs.utils.idempotency import idem_cache
from vendor_libs.utils.observability import (
    jlog,
    metrics_app,
    runs_failed,
    runs_started,
    runs_succeeded,
)
from vendor_libs.utils.runstore import run_store
from vendor_libs.utils.security import (
    ReplaySet,
    SignatureInfo,
    parse_signature_header,
    verify_hmac_sha256,
)
from app.database import get_session
from app.models import Run


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
    """Attach request id, structured logging, and timing information."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        setattr(request.state, "request_id", request_id)
        setattr(request.state, "log_context", {})

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            extra = getattr(request.state, "log_context", {}) or {}
            jlog(
                level="error",
                msg="request",
                request_id=request_id,
                method=request.method,
                path=str(request.url.path),
                status=500,
                dur_ms=duration_ms,
                **extra,
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            response.headers["X-Request-ID"] = request_id
        except Exception:
            pass

        status_code = getattr(response, "status_code", 200)
        level = "error" if status_code >= 500 else "info"
        extra = getattr(request.state, "log_context", {}) or {}
        jlog(
            level=level,
            msg="request",
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
            status=status_code,
            dur_ms=duration_ms,
            **extra,
        )

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


# Global state
_rate_bucket: Dict[tuple[str, int], int] = {}
_rate_lock = Lock()
_jobs: Dict[str, JobRecord] = {}
_processor_runs: Dict[str, Dict[str, Any]] = {}

RUN_MAX_FILES = int(os.getenv("RUN_MAX_FILES", "20"))
RUN_MAX_FILE_MB = int(os.getenv("RUN_MAX_FILE_MB", str(settings.MAX_FILE_MB)))
RUN_MAX_FILE_BYTES = RUN_MAX_FILE_MB * 1024 * 1024
RUN_ALLOWED_MIME_TYPES = {"application/pdf"}
WEBHOOK_REPLAY_WINDOW_S = int(os.getenv("WEBHOOK_REPLAY_WINDOW_S", "300"))
WEBHOOK_REPLAY_TTL_S = int(os.getenv("WEBHOOK_REPLAY_TTL_S", "600"))
webhook_replay_set = ReplaySet(ttl_seconds=WEBHOOK_REPLAY_TTL_S)


def _normalize_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _sync_run_cache(run: Run) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "id": run.id,
        "run_id": run.id,
        "processor": run.processor,
        "processor_name": run.processor,
        "tenant_id": run.tenant_id or "public",
        "status": run.status,
        "created_at": _normalize_iso(run.created_at),
        "updated_at": _normalize_iso(run.updated_at),
        "vendor_job_id": run.vendor_job_id,
        "output": run.output,
        "error": run.error,
        "idempotency_key": run.idempotency_key,
    }
    run_store.put_run(run.id, snapshot)
    if run.vendor_job_id:
        run_store.link_vendor_job(run.vendor_job_id, run.id)
    _processor_runs[run.id] = dict(snapshot)
    return snapshot


def _build_run_response(run: Run) -> Dict[str, Any]:
    return {
        "id": run.id,
        "run_id": run.id,
        "processor": run.processor,
        "status": run.status,
        "created_at": _normalize_iso(run.created_at),
        "updated_at": _normalize_iso(run.updated_at),
        "vendor_job_id": run.vendor_job_id,
        "idempotency_key": run.idempotency_key,
    }


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the configured size limit."""

    def __init__(self, filename: str, limit_bytes: int) -> None:
        self.filename = filename
        self.limit_bytes = limit_bytes
        limit_mb = limit_bytes / (1024 * 1024)
        super().__init__(f"{filename} exceeds {limit_mb:.2f} MB limit")


class LimitedUploadFile:
    """Proxy around UploadFile that tracks bytes read to enforce a limit."""

    def __init__(self, upload: UploadFile, limit_bytes: int, chunk_size: int = 65536) -> None:
        self._upload = upload
        self._limit = limit_bytes
        self._chunk_size = chunk_size
        self._consumed = 0

    @property
    def filename(self) -> Optional[str]:
        return self._upload.filename

    @property
    def content_type(self) -> Optional[str]:
        return self._upload.content_type

    async def prepare(self) -> None:
        """Reset internal counters and rewind the underlying file."""
        await self._upload.seek(0)
        if hasattr(self._upload, "file") and hasattr(self._upload.file, "seek"):
            self._upload.file.seek(0)
        self._consumed = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._chunk_size
        chunk = self._upload.file.read(size)
        self._consumed += len(chunk)
        if self._consumed > self._limit:
            raise FileTooLargeError(self.filename or "upload.pdf", self._limit)
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence not in (0,):
            raise ValueError("LimitedUploadFile only supports whence=0 seeks")
        if hasattr(self._upload, "file") and hasattr(self._upload.file, "seek"):
            position = self._upload.file.seek(offset, whence)
            if position == 0:
                self._consumed = 0
            return position
        if offset == 0:
            self._consumed = 0
        return offset

    async def close(self) -> None:
        await self._upload.close()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._upload, item)


async def _close_uploads(files: Sequence[Any]) -> None:
    for upload in files:
        try:
            await upload.close()  # type: ignore[func-returns-value]
        except Exception:
            pass


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
    app = FastAPI(
        title="PDF Usage Extraction Service",
        version="0.1.0",
        description="Extract internet usage data from telecom PDF invoices",
        root_path="/api"  # For Vercel routing
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
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(FileSizeMiddleware)

    app.add_api_route("/metrics", metrics_app(), methods=["GET"], include_in_schema=False)
    
    # Global router instance
    global router_engine
    router_engine = ExtractionRouter()
    logger = get_logger()

    @app.on_event("startup")
    async def startup_event() -> None:
        """Log service startup information."""
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
                    "cors_origins": settings.get_cors_origins(),
                    "api_base": settings.API_BASE,
                }
            },
        )

    # Health endpoint (public)
    @app.get("/alg/healthz", tags=["health", "legacy"], deprecated=True)
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

    # File upload endpoint (protected)
    @app.post(
        "/extract/upload",
        response_model=ExtractResponse,
        tags=["legacy", "processors"],
        deprecated=True,
    )
    async def extract_upload(
        request: Request,
        files: List[UploadFile] = File(...),
        provider_hint: Optional[str] = Query(default=None),
        debug: bool = Query(default=False),
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
        tags=["legacy", "processors"],
        deprecated=True,
    )
    async def extract_path_endpoint(
        request: Request,
        payload: PathRequest = Body(...),
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
        tags=["legacy", "runs"],
        deprecated=True,
    )
    async def create_job(
        request: Request,
        payload: JobCreate,
        background_tasks: BackgroundTasks,
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
        tags=["legacy", "runs"],
        deprecated=True,
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
        tags=["runs"],
        responses={
            200: {
                "description": "Run queued",
                "content": {
                    "application/json": {
                        "examples": {
                            "queued": {
                                "summary": "Queued run",
                                "value": {
                                    "id": "run_abcd1234ef56",
                                    "run_id": "run_abcd1234ef56",
                                    "processor": "usage_extractor",
                                    "status": "queued",
                                    "created_at": "2024-05-01T12:00:00Z",
                                    "vendor_job_id": "job_789def",
                                    "idempotency_key": "alpha-123"
                                },
                            }
                        }
                    }
                },
            }
        },
    )
    async def create_processor_run(
        processor_name: str,
        request: Request,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_session),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        files: Optional[List[UploadFile]] = File(default=None),
        x_api_version: Optional[str] = Header(default=None),
        idem_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> Dict[str, Any]:
        """Create a processor run (Algorythmos-style endpoint)."""

        if x_api_version:
            logger.info(
                "API version requested",
                extra={"context": {"version": x_api_version, "processor": processor_name}},
            )

        tenant_id = tenant_ctx.get("tenant", "unknown")
        uploads = list(files or [])
        content_type = request.headers.get("content-type", "")
        is_json_body = content_type.startswith("application/json")

        idem_key = (idem_key or "").strip() or None
        cache_key: Optional[str] = None
        if idem_key:
            cache_key = f"{tenant_id}:{processor_name}:{idem_key}"
            cached_response = idem_cache.get(cache_key)
            if cached_response:
                await _close_uploads(uploads)
                logger.info(
                    "Idempotent processor run replay",
                    extra={
                        "context": {
                            "processor": processor_name,
                            "tenant_id": tenant_id,
                            "idempotency_key": idem_key,
                            "run_id": cached_response.get("id") or cached_response.get("run_id"),
                        }
                    },
                )
                return cached_response

        if is_json_body and not uploads:
            payload_data = await request.json()
            payload = JobCreate.model_validate(payload_data)

            run_id = str(uuid4())
            job_record = JobRecord(
                job_id=run_id,
                status="queued",
                tenant_id=tenant_id,
                request_id=getattr(request.state, "request_id", None),
                created_at=_utcnow(),
                updated_at=_utcnow(),
                webhook_url=payload.webhook_url,
            )
            _jobs[run_id] = job_record

            background_tasks.add_task(_execute_job, run_id, payload, tenant_id, job_record.request_id)

        response_payload = {
            "id": run_id,
            "run_id": run_id,
            "processor": processor_name,
            "processor_name": processor_name,
            "status": job_record.status,
            "created_at": job_record.created_at.isoformat(),
            "tenant_id": tenant_id,
        }
        if idem_key:
            response_payload["idempotency_key"] = idem_key

        if hasattr(request.state, "log_context"):
            request.state.log_context.update({"run_id": run_id, "processor": processor_name})
        runs_started.labels(processor_name).inc()

        run_snapshot = dict(response_payload)
        run_snapshot["updated_at"] = job_record.updated_at.isoformat()
        run_store.put_run(run_id, run_snapshot)
        _processor_runs[run_id] = dict(run_snapshot)

        logger.info(
            "Processor run queued",
            extra={
                "context": {
                    "run_id": run_id,
                    "processor": processor_name,
                    "tenant_id": tenant_id,
                    "request_id": job_record.request_id,
                    "api_version": x_api_version,
                }
            },
        )

        if cache_key:
            idem_cache.put(cache_key, response_payload)

        return response_payload

        if not uploads:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "NO_FILES", "message": "At least one PDF file must be uploaded"},
            )

        if len(uploads) > RUN_MAX_FILES:
            await _close_uploads(uploads)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "TOO_MANY_FILES", "message": f"Too many files provided (max {RUN_MAX_FILES})"},
            )

        for upload in uploads:
            if not upload.content_type or upload.content_type.lower() not in RUN_ALLOWED_MIME_TYPES:
                await _close_uploads(uploads)
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail={
                        "code": "UNSUPPORTED_MEDIA_TYPE",
                        "message": f"Unsupported content type {upload.content_type!r}; only application/pdf is allowed",
                    },
                )

        existing_run: Optional[Run] = None
        if idem_key:
            stmt = select(Run).where(
                Run.tenant_id == tenant_id,
                Run.processor == processor_name,
                Run.idempotency_key == idem_key,
            )
            result = await session.execute(stmt)
            existing_run = result.scalar_one_or_none()

        if existing_run:
            await _close_uploads(uploads)
            _sync_run_cache(existing_run)
            if hasattr(request.state, "log_context"):
                request.state.log_context.update({"run_id": existing_run.id, "processor": processor_name})
            response_payload = _build_run_response(existing_run)
            if cache_key:
                idem_cache.put(cache_key, response_payload)
            return response_payload

        run_id = f"run_{secrets.token_hex(6)}"
        run = Run(
            id=run_id,
            processor=processor_name,
            tenant_id=tenant_id,
            status="queued",
            idempotency_key=idem_key,
        )
        session.add(run)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            stmt = select(Run).where(
                Run.tenant_id == tenant_id,
                Run.processor == processor_name,
                Run.idempotency_key == idem_key,
            )
            result = await session.execute(stmt)
            run = result.scalar_one()
            await _close_uploads(uploads)
            _sync_run_cache(run)
            if hasattr(request.state, "log_context"):
                request.state.log_context.update({"run_id": run.id, "processor": processor_name})
            response_payload = _build_run_response(run)
            if cache_key:
                idem_cache.put(cache_key, response_payload)
            return response_payload

        limited_files: List[LimitedUploadFile] = []

        def _resolve_input_path(metadata: Optional[Dict[str, Any]]) -> str:
            if isinstance(metadata, dict):
                for key in ("input_path", "path", "upload_path", "upload_id", "id", "resource"):
                    value = metadata.get(key)
                    if isinstance(value, str) and value:
                        return value
            return f"upload:{run_id}"

        vendor_job_id: Optional[str] = None
        try:
            for upload in uploads:
                limited = LimitedUploadFile(upload, RUN_MAX_FILE_BYTES)
                await limited.prepare()
                limited_files.append(limited)

            upload_metadata = await vendor_services.upload_files_stream(limited_files)
            input_path = _resolve_input_path(upload_metadata)
            job_payload = {
                "processor": processor_name,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "files": len(uploads),
            }
            vendor_job = await vendor_services.create_job(
                input_path,
                job_payload,
                tenant_id=tenant_id,
            )
            vendor_job_id = vendor_job.get("job_id")
            if not isinstance(vendor_job_id, str) or not vendor_job_id:
                raise ValueError("Vendor response missing job_id")
            run.vendor_job_id = vendor_job_id
        except FileTooLargeError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "code": "FILE_TOO_LARGE",
                    "message": f"{exc.filename} exceeds {RUN_MAX_FILE_MB} MB limit",
                },
            ) from exc
        except httpx.HTTPStatusError as exc:
            await session.rollback()
            logger.warning(
                "Vendor upload failed",
                extra={
                    "context": {
                        "processor": processor_name,
                        "tenant_id": tenant_id,
                        "status_code": exc.response.status_code,
                    }
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "VENDOR_UPLOAD_FAILED", "message": "Vendor upload failed"},
            ) from exc
        except httpx.HTTPError as exc:
            await session.rollback()
            logger.warning(
                "Vendor upload unreachable",
                extra={"context": {"processor": processor_name, "tenant_id": tenant_id}},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "VENDOR_UPLOAD_FAILED", "message": "Vendor service unreachable"},
            ) from exc
        except ValueError as exc:
            await session.rollback()
            logger.warning(
                "Vendor job creation failed",
                extra={"context": {"processor": processor_name, "tenant_id": tenant_id}},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "VENDOR_JOB_FAILED", "message": str(exc)},
            ) from exc
        finally:
            await _close_uploads(limited_files)

        await session.commit()
        await session.refresh(run)

        _sync_run_cache(run)
        if hasattr(request.state, "log_context"):
            request.state.log_context.update({"run_id": run.id, "processor": processor_name})
        runs_started.labels(processor_name).inc()
        response_payload = _build_run_response(run)

        logger.info(
            "Processor run accepted",
            extra={
                "context": {
                    "processor": processor_name,
                    "tenant_id": tenant_id,
                    "run_id": run.id,
                    "files": len(uploads),
                    "idempotent": bool(idem_key),
                }
            },
        )

        if cache_key:
            idem_cache.put(cache_key, response_payload)

        return response_payload

    @app.get(
        "/processors/{processor_name}/runs/{run_id}",
        tags=["runs"],
        responses={
            200: {
                "description": "Run status and output",
                "content": {
                    "application/json": {
                        "examples": {
                            "extract": {
                                "summary": "Succeeded run (EXTRACT)",
                                "value": {
                                    "id": "run_abcd1234ef56",
                                    "run_id": "run_abcd1234ef56",
                                    "processor": "usage_extractor",
                                    "status": "succeeded",
                                    "created_at": "2024-05-01T12:00:00Z",
                                    "updated_at": "2024-05-01T12:01:12Z",
                                    "vendor_job_id": "job_789def",
                                    "output": {
                                        "fields": [
                                            {
                                                "name": "invoice_number",
                                                "value": "A-123",
                                                "confidence": 0.98,
                                                "citations": [
                                                    {"page": 1, "x": 122, "y": 540, "w": 90, "h": 20}
                                                ],
                                            }
                                        ],
                                        "tables": [
                                            {
                                                "name": "line_items",
                                                "rows": [
                                                    {"desc": "SIM", "qty": 2, "price": 10.0}
                                                ],
                                            }
                                        ],
                                        "pages": 3,
                                    },
                                },
                            },
                            "failed": {
                                "summary": "Failed run",
                                "value": {
                                    "id": "run_failed123",
                                    "run_id": "run_failed123",
                                    "processor": "usage_extractor",
                                    "status": "failed",
                                    "created_at": "2024-05-01T12:00:00Z",
                                    "updated_at": "2024-05-01T12:00:30Z",
                                    "vendor_job_id": "job_failed123",
                                    "error": {
                                        "code": "VENDOR_TIMEOUT",
                                        "message": "Upstream vendor timed out"
                                    },
                                },
                            },
                        }
                    }
                },
            }
        },
    )
    async def get_processor_run(
        processor_name: str,
        run_id: str,
        session: AsyncSession = Depends(get_session),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        """Get processor run status and results (Algorythmos-style endpoint)."""

        tenant_id = tenant_ctx.get("tenant")

        db_run = await session.get(Run, run_id)
        if db_run and db_run.processor == processor_name and (tenant_id is None or db_run.tenant_id == tenant_id):
            response = _build_run_response(db_run)
            if db_run.output is not None:
                response["output"] = db_run.output
            if db_run.error is not None:
                response["error"] = db_run.error
            _sync_run_cache(db_run)
            return response

        run_snapshot = run_store.get_run(run_id)
        if run_snapshot and run_snapshot.get("tenant_id") == tenant_id:
            created_at = run_snapshot.get("created_at")
            updated_at = run_snapshot.get("updated_at")
            if isinstance(updated_at, (int, float)):
                updated_at = datetime.fromtimestamp(updated_at, timezone.utc).isoformat()

            response: Dict[str, Any] = {
                "id": run_id,
                "run_id": run_id,
                "processor": processor_name,
                "processor_name": run_snapshot.get("processor_name", processor_name),
                "tenant_id": tenant_id,
                "status": run_snapshot.get("status", "queued"),
            }
            if created_at:
                response["created_at"] = created_at
            if updated_at:
                response["updated_at"] = updated_at
            if run_snapshot.get("vendor_job_id"):
                response["vendor_job_id"] = run_snapshot["vendor_job_id"]
            if run_snapshot.get("idempotency_key"):
                response["idempotency_key"] = run_snapshot["idempotency_key"]
            if isinstance(run_snapshot.get("output"), dict):
                response["output"] = run_snapshot["output"]
            if run_snapshot.get("error") is not None:
                response["error"] = run_snapshot["error"]
            return response

        job = _jobs.get(run_id)
        if job and job.tenant_id == tenant_id:
            response = {
                "run_id": run_id,
                "processor_name": processor_name,
                "status": job.status,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
                "tenant_id": job.tenant_id,
            }
            if job.result:
                response["output"] = job.result.model_dump(mode="json")
            if job.error:
                response["error"] = job.error
            if job.duration_sec:
                response["duration_sec"] = job.duration_sec
            return response

        run_entry = _processor_runs.get(run_id)
        if run_entry and run_entry.get("tenant_id") == tenant_id:
            run_details = dict(run_entry)
            base_output: Dict[str, Any] = {"ok": True}
            if isinstance(run_details.get("output"), dict):
                base_output.update(run_details["output"])

            response = {
                "id": run_id,
                "run_id": run_id,
                "processor": processor_name,
                "processor_name": processor_name,
                "tenant_id": tenant_id,
                "status": run_details.get("status", "succeeded"),
                "output": base_output,
            }
            if run_details.get("created_at"):
                response["created_at"] = run_details["created_at"]
            if run_details.get("updated_at"):
                response["updated_at"] = run_details["updated_at"]
            if run_details.get("vendor_job_id"):
                response["vendor_job_id"] = run_details["vendor_job_id"]
            return response

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RUN_NOT_FOUND", "message": "Run not found"},
        )

    @app.post(
        "/webhooks/vendor",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["webhooks"],
    )
    async def vendor_webhook(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
        """Handle vendor callbacks with HMAC validation and replay protection."""

        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Webhook must be application/json"},
            )

        raw_body = await request.body()
        secret = settings.VENDOR_WEBHOOK_SECRET
        signature_header = request.headers.get("X-Vendor-Signature")
        sig_info = parse_signature_header(signature_header)
        now = int(time.time())

        def _unauthorized(reason: str) -> HTTPException:
            logger.warning(
                "Vendor webhook unauthorized",
                extra={"context": {"reason": reason}},
            )
            return HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_SIGNATURE", "message": reason},
            )

        if not sig_info:
            raise _unauthorized("Missing or malformed signature header")

        if sig_info.scheme == "legacy":
            ts_header = request.headers.get("X-Vendor-Timestamp")
            if ts_header is None:
                raise _unauthorized("Legacy signature requires X-Vendor-Timestamp")
            try:
                legacy_timestamp = int(ts_header)
            except ValueError:
                raise _unauthorized("Invalid timestamp format")
            if abs(now - legacy_timestamp) > WEBHOOK_REPLAY_WINDOW_S:
                raise _unauthorized("Signature timestamp outside allowed window")
            sig_info = SignatureInfo(
                scheme="legacy",
                signature=sig_info.signature,
                timestamp=legacy_timestamp,
            )
        elif sig_info.scheme == "v1":
            if sig_info.timestamp is None:
                raise _unauthorized("v1 signature missing timestamp")
            if abs(now - sig_info.timestamp) > WEBHOOK_REPLAY_WINDOW_S:
                raise _unauthorized("Signature timestamp outside allowed window")
        else:
            raise _unauthorized("Unsupported signature scheme")

        if not verify_hmac_sha256(
            raw_body,
            sig_info,
            secret,
            now=now,
            replay_window_s=WEBHOOK_REPLAY_WINDOW_S,
        ):
            raise _unauthorized("Signature verification failed")

        dedupe_key = request.headers.get("X-Vendor-Event-ID")
        if dedupe_key:
            dedupe_key = f"event:{dedupe_key}"
        else:
            dedupe_key = f"body:{hashlib.sha256(raw_body).hexdigest()}"

        if not webhook_replay_set.seen_once(dedupe_key):
            logger.info(
                "Vendor webhook replay",
                extra={"context": {"replay": True, "key": dedupe_key}},
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_JSON", "message": "Malformed JSON payload"},
            ) from exc

        job_id = payload.get("job_id")
        status_value = payload.get("status")
        if not isinstance(job_id, str) or not job_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "MISSING_JOB_ID", "message": "Webhook payload missing job_id"},
            )
        if status_value not in {"succeeded", "failed"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_STATUS", "message": "Webhook payload contains invalid status"},
            )

        stmt = select(Run).where(Run.vendor_job_id == job_id)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            logger.info(
                "Vendor webhook for unknown job",
                extra={"context": {"vendor_job_id": job_id}},
            )
            return Response(status_code=status.HTTP_204_NO_CONTENT)

        if status_value == "succeeded":
            run.status = "succeeded"
            run.output = payload.get("output")
            run.error = None
        else:
            run.status = "failed"
            run.error = payload.get("error")
            run.output = None

        if hasattr(request.state, "log_context"):
            request.state.log_context.update({"run_id": run.id, "processor": run.processor})

        await session.commit()
        await session.refresh(run)

        _sync_run_cache(run)

        if status_value == "succeeded":
            runs_succeeded.labels(run.processor).inc()
        else:
            runs_failed.labels(run.processor).inc()

        logger.info(
            "Vendor webhook processed",
            extra={
                "context": {
                    "vendor_job_id": job_id,
                    "run_id": run.id,
                    "status": status_value,
                    "replay": False,
                }
            },
        )

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.patch(
        "/processors/{processor_name}",
        tags=["processors"],
    )
    async def update_processor(
        processor_name: str,
        request: Request,
        payload: Dict[str, Any] = Body(...),
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None),
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

    # Shutdown handler for HTTP client cleanup
    @app.on_event("shutdown")
    async def shutdown_event():
        """Clean up resources on shutdown."""
        try:
            from vendor_libs.utils.http import close_http_client
            await close_http_client()
        except Exception:
            pass  # Don't fail shutdown on cleanup errors

    return app


# Create the app instance
app = build_api()
