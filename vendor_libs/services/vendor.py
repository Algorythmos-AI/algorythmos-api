"""Vendor service with resilient HTTP operations."""

from typing import Any, Dict, List, Optional
from pathlib import Path

import httpx

from ..utils.http import vendor_client, with_retries
from config import settings


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
                    response = await client.get(
                        f"{self.base_url}/health",
                        timeout=2.0  # Quick health check
                    )
                    response.raise_for_status()
                    return response.status_code == 200
            
            # For health checks, use minimal retries (2 attempts)
            return await with_retries(_health, attempts=2, base_delay=0.1)
        except Exception:
            # Health check failures should not raise exceptions
            return False


# Global vendor service instance
vendor_service = VendorService()