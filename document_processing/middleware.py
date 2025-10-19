"""
Middleware for production features.

Includes:
- Rate limiting
- Idempotency handling
- Request tracking
"""

import hashlib
import time
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional, Tuple

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# In-memory stores (in production, use Redis)
_rate_limit_store: Dict[str, list] = defaultdict(list)
_rate_limit_lock = Lock()

_idempotency_store: Dict[str, Tuple[int, dict, datetime]] = {}
_idempotency_lock = Lock()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware.
    
    Limits requests per tenant based on time windows.
    Uses token bucket algorithm.
    """
    
    def __init__(self, app, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics", "/api/health"]:
            return await call_next(request)
        
        # Get tenant identifier (from API key or other auth)
        tenant_id = self._get_tenant_id(request)
        
        if not tenant_id:
            # No tenant ID, proceed without rate limiting
            return await call_next(request)
        
        # Check rate limits
        now = time.time()
        
        with _rate_limit_lock:
            # Get request timestamps for this tenant
            timestamps = _rate_limit_store[tenant_id]
            
            # Remove old timestamps (older than 1 hour)
            cutoff_hour = now - 3600
            timestamps[:] = [ts for ts in timestamps if ts > cutoff_hour]
            
            # Check hourly limit
            if len(timestamps) >= self.requests_per_hour:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "type": "rate_limit_exceeded",
                            "message": "Too many requests. Hourly limit exceeded.",
                            "details": {
                                "limit": self.requests_per_hour,
                                "window": "1 hour",
                                "retry_after": int(timestamps[0] + 3600 - now)
                            }
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(self.requests_per_hour),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(timestamps[0] + 3600)),
                        "Retry-After": str(int(timestamps[0] + 3600 - now))
                    }
                )
            
            # Check per-minute limit
            cutoff_minute = now - 60
            recent_requests = [ts for ts in timestamps if ts > cutoff_minute]
            
            if len(recent_requests) >= self.requests_per_minute:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "type": "rate_limit_exceeded",
                            "message": "Too many requests. Per-minute limit exceeded.",
                            "details": {
                                "limit": self.requests_per_minute,
                                "window": "1 minute",
                                "retry_after": int(recent_requests[0] + 60 - now)
                            }
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(self.requests_per_minute),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": str(int(recent_requests[0] + 60 - now))
                    }
                )
            
            # Record this request
            timestamps.append(now)
            
            # Calculate remaining requests
            remaining_minute = self.requests_per_minute - len(recent_requests) - 1
            remaining_hour = self.requests_per_hour - len(timestamps)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, remaining_minute))
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, remaining_hour))
        
        return response
    
    def _get_tenant_id(self, request: Request) -> Optional[str]:
        """Extract tenant ID from request."""
        # Try to get from state (set by auth middleware)
        if hasattr(request.state, "tenant_id"):
            return request.state.tenant_id
        
        # Try to extract from API key header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # In production, decode/validate the API key to get tenant ID
            # For now, use hash of API key as tenant ID
            return hashlib.sha256(api_key.encode()).hexdigest()[:16]
        
        return None


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    Idempotency middleware.
    
    Handles idempotency keys for POST/PUT/PATCH requests.
    Stores responses and returns cached responses for duplicate requests.
    """
    
    def __init__(self, app, ttl_seconds: int = 86400):  # 24 hours default
        super().__init__(app)
        self.ttl_seconds = ttl_seconds
    
    async def dispatch(self, request: Request, call_next):
        # Only handle POST/PUT/PATCH requests
        if request.method not in ["POST", "PUT", "PATCH"]:
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get("Idempotency-Key")
        
        if not idempotency_key:
            # No idempotency key, process normally
            return await call_next(request)
        
        # Create cache key (include tenant ID if available)
        tenant_id = self._get_tenant_id(request)
        cache_key = f"{tenant_id}:{idempotency_key}" if tenant_id else idempotency_key
        
        # Check if we've seen this request before
        with _idempotency_lock:
            if cache_key in _idempotency_store:
                status_code, response_data, created_at = _idempotency_store[cache_key]
                
                # Check if cached response is still valid
                age = (datetime.utcnow() - created_at).total_seconds()
                if age < self.ttl_seconds:
                    # Return cached response
                    return JSONResponse(
                        status_code=status_code,
                        content=response_data,
                        headers={
                            "X-Idempotency-Replay": "true",
                            "X-Idempotency-Age": str(int(age))
                        }
                    )
                else:
                    # Cached response expired, remove it
                    del _idempotency_store[cache_key]
        
        # Process request
        response = await call_next(request)
        
        # Cache successful responses (2xx status codes)
        if 200 <= response.status_code < 300:
            # Read response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # Parse JSON response
            import json
            try:
                response_data = json.loads(body.decode())
                
                # Store in cache
                with _idempotency_lock:
                    _idempotency_store[cache_key] = (
                        response.status_code,
                        response_data,
                        datetime.utcnow()
                    )
                    
                    # Cleanup old entries (simple LRU-like behavior)
                    if len(_idempotency_store) > 10000:
                        # Remove oldest 10%
                        sorted_keys = sorted(
                            _idempotency_store.keys(),
                            key=lambda k: _idempotency_store[k][2]
                        )
                        for key in sorted_keys[:1000]:
                            del _idempotency_store[key]
                
                # Return response with new body
                return JSONResponse(
                    status_code=response.status_code,
                    content=response_data,
                    headers=dict(response.headers)
                )
            
            except Exception:
                # Failed to cache, return original response
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        
        return response
    
    def _get_tenant_id(self, request: Request) -> Optional[str]:
        """Extract tenant ID from request."""
        if hasattr(request.state, "tenant_id"):
            return request.state.tenant_id
        
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return hashlib.sha256(api_key.encode()).hexdigest()[:16]
        
        return None


def cleanup_old_entries():
    """
    Cleanup old entries from in-memory stores.
    
    Should be called periodically (e.g., via scheduled task).
    """
    now = time.time()
    cutoff = now - 3600  # 1 hour
    
    # Cleanup rate limit store
    with _rate_limit_lock:
        for tenant_id in list(_rate_limit_store.keys()):
            timestamps = _rate_limit_store[tenant_id]
            timestamps[:] = [ts for ts in timestamps if ts > cutoff]
            
            # Remove empty entries
            if not timestamps:
                del _rate_limit_store[tenant_id]
    
    # Cleanup idempotency store
    cutoff_datetime = datetime.utcnow() - timedelta(hours=24)
    
    with _idempotency_lock:
        expired_keys = [
            key for key, (_, _, created_at) in _idempotency_store.items()
            if created_at < cutoff_datetime
        ]
        
        for key in expired_keys:
            del _idempotency_store[key]
