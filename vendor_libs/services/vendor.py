"""Vendor service with resilient HTTP operations."""

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
from pathlib import Path

import httpx
from vendor_libs.utils.observability import vendor_latency
from starlette.datastructures import UploadFile

from ..utils.http import vendor_client, with_retries
from config import settings

Json = Dict[str, Any]


class VendorService:
    """Service for resilient vendor API operations."""
    
    def __init__(self, base_url: str = "https://api.vendor.example"):
        self.base_url = base_url.rstrip("/")
    
    async def upload_files(
        self, 
        files: List[Dict[str, Any]], 
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload files to vendor with automatic retries."""
        
        async def _upload():
            async with vendor_client() as client:
                headers = {"Content-Type": "application/json"}
                if tenant_id:
                    headers["X-Tenant-ID"] = tenant_id
                
                response = await client.post(
                    f"{self.base_url}/upload",
                    json={"files": files},
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
        
        return await with_retries(_upload)
    
    async def resolve_path(self, path: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a file path with vendor with automatic retries."""
        
        async def _resolve():
            async with vendor_client() as client:
                headers = {}
                if tenant_id:
                    headers["X-Tenant-ID"] = tenant_id
                
                response = await client.post(
                    f"{self.base_url}/resolve",
                    json={"path": path},
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
        
        return await with_retries(_resolve)
    
    async def create_job(
        self, 
        job_data: Dict[str, Any], 
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a job with vendor with automatic retries."""
        
        async def _create():
            async with vendor_client() as client:
                headers = {"Content-Type": "application/json"}
                if tenant_id:
                    headers["X-Tenant-ID"] = tenant_id
                
                response = await client.post(
                    f"{self.base_url}/jobs",
                    json=job_data,
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
        
        return await with_retries(_create)
    
    async def get_job(self, job_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Get job status from vendor with automatic retries."""
        
        async def _get():
            async with vendor_client() as client:
                headers = {}
                if tenant_id:
                    headers["X-Tenant-ID"] = tenant_id
                
                response = await client.get(
                    f"{self.base_url}/jobs/{job_id}",
                    headers=headers
                )
                response.raise_for_status()
                return response.json()
        
        return await with_retries(_get)
    
    async def vendor_health_check(self) -> bool:
        """Check vendor health - returns True if healthy, False otherwise."""
        try:
            async def _health():
                async with vendor_client() as client:
                    start = time.perf_counter()
                    try:
                        response = await client.get(
                            f"{self.base_url}/health",
                            timeout=2.0  # Quick health check
                        )
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        vendor_latency.labels("GET", "/health", str(exc.response.status_code)).observe(
                            time.perf_counter() - start
                        )
                        raise
                    except Exception:
                        vendor_latency.labels("GET", "/health", "error").observe(
                            time.perf_counter() - start
                        )
                        raise
                    else:
                        vendor_latency.labels("GET", "/health", str(response.status_code)).observe(
                            time.perf_counter() - start
                        )
                        return response.status_code == 200
            
            # For health checks, use minimal retries (2 attempts)
            return await with_retries(_health, attempts=2, base_delay=0.1)
        except Exception:
            # Health check failures should not raise exceptions
            return False


async def upload_files_stream(files: Sequence[Any]) -> Json:
    if not files:
        raise ValueError("At least one file must be provided for upload.")

    async def _do():
        async with vendor_client() as client:
            form_files: List[Tuple[str, Tuple[str, Any, str]]] = [
                (
                    "files",
                    (
                        up.filename or "upload.pdf",
                        up,
                        up.content_type or "application/pdf",
                    ),
                )
                for up in files
            ]
            endpoint = "/extract/upload"
            start = time.perf_counter()
            try:
                resp = await client.post(
                    f"{vendor_service.base_url}{endpoint}",
                    files=form_files,
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                vendor_latency.labels("POST", endpoint, str(exc.response.status_code)).observe(
                    time.perf_counter() - start
                )
                raise
            except Exception:
                vendor_latency.labels("POST", endpoint, "error").observe(
                    time.perf_counter() - start
                )
                raise
            else:
                vendor_latency.labels("POST", endpoint, str(resp.status_code)).observe(
                    time.perf_counter() - start
                )
                return resp.json()

    return await with_retries(_do)


async def create_job(
    input_path: str,
    payload: Dict[str, Any],
    *,
    tenant_id: Optional[str] = None,
) -> Json:
    """Create a vendor job for the given input path and payload."""

    job_body: Dict[str, Any] = {"input_path": input_path}
    job_body.update(payload)

    async def _do() -> Json:
        async with vendor_client() as client:
            headers = {"Content-Type": "application/json"}
            if tenant_id:
                headers["X-Tenant-ID"] = tenant_id

            endpoint = "/jobs"
            start = time.perf_counter()
            try:
                response = await client.post(
                    f"{vendor_service.base_url}{endpoint}",
                    json=job_body,
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                vendor_latency.labels("POST", endpoint, str(exc.response.status_code)).observe(
                    time.perf_counter() - start
                )
                raise
            except Exception:
                vendor_latency.labels("POST", endpoint, "error").observe(
                    time.perf_counter() - start
                )
                raise
            else:
                vendor_latency.labels("POST", endpoint, str(response.status_code)).observe(
                    time.perf_counter() - start
                )
                return response.json()

    result = await with_retries(_do)
    if "job_id" not in result:
        raise ValueError("Vendor response missing job_id")
    return result


# Global vendor service instance
vendor_service = VendorService()
