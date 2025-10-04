"""Main application factory for the PDF Usage Extraction Service."""

from __future__ import annotations

import os
import tempfile
import time
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


# Global state
_rate_bucket: Dict[tuple[str, int], int] = {}
_rate_lock = Lock()
_jobs: Dict[str, JobRecord] = {}


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
        allow_headers=["*"],
    )
    app.add_middleware(FileSizeMiddleware)
    app.add_middleware(RequestContextMiddleware)
    
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

    # File upload endpoint (protected)
    @app.post("/extract/upload", response_model=ExtractResponse)
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
    @app.post("/extract/path", response_model=ExtractResponse)
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
    @app.post("/jobs")
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
    @app.get("/jobs/{job_id}")
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
    @app.post("/processors/{processor_name}/runs")
    async def create_processor_run(
        processor_name: str,
        request: Request,
        payload: JobCreate,
        background_tasks: BackgroundTasks,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        """Create a processor run (Algorythmos-style endpoint)."""
        # Log API version if provided
        if x_api_version:
            logger.info(
                "API version requested",
                extra={"context": {"version": x_api_version, "processor": processor_name}},
            )

        run_id = str(uuid4())
        job_record = JobRecord(
            job_id=run_id,
            status="queued",
            tenant_id=tenant_ctx["tenant"],
            request_id=getattr(request.state, "request_id", None),
            created_at=_utcnow(),
            updated_at=_utcnow(),
            webhook_url=payload.webhook_url,
        )
        _jobs[run_id] = job_record

        background_tasks.add_task(_execute_job, run_id, payload, tenant_ctx["tenant"], job_record.request_id)

        logger.info(
            "Processor run queued",
            extra={
                "context": {
                    "run_id": run_id,
                    "processor": processor_name,
                    "tenant_id": tenant_ctx["tenant"],
                    "request_id": job_record.request_id,
                    "api_version": x_api_version,
                }
            },
        )
        
        # Return Algorythmos-compatible response
        return {
            "run_id": run_id,
            "processor_name": processor_name,
            "status": job_record.status,
            "created_at": job_record.created_at.isoformat(),
            "tenant_id": tenant_ctx["tenant"],
        }

    @app.get("/processors/{processor_name}/runs/{run_id}")
    async def get_processor_run(
        processor_name: str,
        run_id: str,
        tenant_ctx: Dict[str, str] = Depends(require_key),
        x_api_version: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        """Get processor run status and results (Algorythmos-style endpoint)."""
        job = _jobs.get(run_id)
        if not job or job.tenant_id != tenant_ctx["tenant"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail={"code": "RUN_NOT_FOUND", "message": "Run not found"}
            )
        
        # Return Algorythmos-compatible response format
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

    @app.patch("/processors/{processor_name}")
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

    return app


# Create the app instance
app = build_api()