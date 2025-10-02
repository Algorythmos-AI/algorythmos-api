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
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.params import Body, Query
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware

from pdf_usage_extractor import ExtractionRouter
from pdf_usage_extractor.logging_utils import get_logger
from pdf_usage_extractor.schemas import ExtractResponse, UsageRecord


class PathRequest(BaseModel):
    input_path: str
    provider_hint: Optional[str] = None
    debug: bool = False


class JobCreate(BaseModel):
    input_path: str
    provider_hint: Optional[str] = None
    debug: bool = False
    webhook_url: Optional[AnyHttpUrl] = None


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


app = FastAPI(title="PDF Usage Extraction Service", version="0.1.0")
router_engine = ExtractionRouter()
logger = get_logger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _get_allowed_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS", "*")
    if raw.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_rate_bucket: Dict[tuple[str, int], int] = {}
_rate_lock = Lock()
_jobs: Dict[str, JobRecord] = {}


@app.on_event("startup")
async def startup_event() -> None:
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
                "rate_per_min": _get_rate_limit(),
                "max_file_mb": _get_max_file_mb(),
            }
        },
    )


def _get_rate_limit() -> int:
    try:
        return int(os.getenv("RATE_PER_MIN", "120"))
    except ValueError:
        return 120


def _get_max_file_mb() -> int:
    try:
        return int(os.getenv("MAX_FILE_MB", "25"))
    except ValueError:
        return 25


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enforce_rate_limit(tenant_id: str) -> None:
    rate = _get_rate_limit()
    if rate <= 0:
        return
    current_window = int(time.time() // 60)
    with _rate_lock:
        stale_keys = [key for key in _rate_bucket if key[1] < current_window]
        for key in stale_keys:
            _rate_bucket.pop(key, None)

        bucket_key = (tenant_id, current_window)
        current = _rate_bucket.get(bucket_key, 0) + 1
        if current > rate:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
        _rate_bucket[bucket_key] = current


async def require_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None),
) -> Dict[str, str]:
    api_key = os.getenv("API_KEY")
    if api_key and x_api_key != api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorised")
    if not x_tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing X-Tenant-Id")

    _enforce_rate_limit(x_tenant_id)
    request.state.tenant_id = x_tenant_id
    return {"tenant": x_tenant_id}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    try:
        from importlib import metadata

        response = {
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
        return {"service": app.version}


async def _run_extraction(
    *,
    path: str,
    provider_hint: Optional[str],
    debug: bool,
) -> tuple[list[UsageRecord], list[str], float]:
    start = time.perf_counter()

    def _execute() -> tuple[list[UsageRecord], list[str]]:
        return router_engine.extract_path(path, provider_hint=provider_hint, debug=debug)

    records, warnings = await anyio.to_thread.run_sync(_execute)
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
        job_logger.debug(
            "Job result ready",
            extra={
                "context": {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "records": result.count,
                    "request_id": request_id,
                }
            },
        )
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


@app.post("/extract/upload", response_model=ExtractResponse)
async def extract_upload(
    request: Request,
    files: List[UploadFile] = File(...),
    provider_hint: Optional[str] = Query(default=None),
    debug: bool = Query(default=False),
    tenant_ctx: Dict[str, str] = Depends(require_key),
) -> ExtractResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")

    max_bytes = _get_max_file_mb() * 1024 * 1024
    with tempfile.TemporaryDirectory(prefix="pdf-extract-") as tmpdir:
        saved_paths: List[str] = []
        for index, upload in enumerate(files):
            if upload.content_type not in {"application/pdf", "application/x-pdf", None}:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported content type: {upload.content_type}",
                )
            original = upload.filename or f"upload-{index}.pdf"
            filename = os.path.basename(original)
            if not filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"File is not a PDF: {filename}")
            dest = os.path.join(tmpdir, f"{index}_{filename}")
            content = await upload.read()
            if not content:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Empty file: {filename}")
            if len(content) > max_bytes:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File exceeds {max_bytes // (1024 * 1024)} MB limit")
            async with await anyio.open_file(dest, "wb") as fp:
                await fp.write(content)
            await upload.close()
            saved_paths.append(dest)

        records, warnings, elapsed = await _run_extraction(
            path=tmpdir,
            provider_hint=provider_hint,
            debug=debug,
        )
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


@app.post("/extract/path", response_model=ExtractResponse)
async def extract_path_endpoint(
    request: Request,
    payload: PathRequest = Body(...),
    tenant_ctx: Dict[str, str] = Depends(require_key),
) -> ExtractResponse:
    resolved = os.path.expanduser(payload.input_path)
    if not os.path.exists(resolved):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Input path not found")

    try:
        records, warnings, elapsed = await _run_extraction(
            path=resolved,
            provider_hint=payload.provider_hint,
            debug=payload.debug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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


@app.post("/jobs")
async def create_job(
    request: Request,
    payload: JobCreate,
    background_tasks: BackgroundTasks,
    tenant_ctx: Dict[str, str] = Depends(require_key),
) -> Dict[str, Any]:
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


@app.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    tenant_ctx: Dict[str, str] = Depends(require_key),
) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job or job.tenant_id != tenant_ctx["tenant"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    return job.model_dump(mode="json")
