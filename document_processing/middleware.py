"""Production middleware for rate limiting and idempotency."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from document_processing.state import (
    IdempotencyStore,
    RateLimitStore,
    build_idempotency_cache_key,
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware backed by pluggable distributed stores."""

    def __init__(
        self,
        app,
        *,
        rate_limit_store: RateLimitStore,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        fail_closed: bool = False,
    ):
        super().__init__(app)
        self.rate_limit_store = rate_limit_store
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.fail_closed = fail_closed

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/health", "/metrics", "/api/health", "/alg/healthz"]:
            return await call_next(request)

        tenant_id = self._get_tenant_id(request)
        if not tenant_id:
            return await call_next(request)

        minute_remaining = self.requests_per_minute
        hour_remaining = self.requests_per_hour
        try:
            minute_decision = await self.rate_limit_store.check_limit(
                tenant_id,
                self.requests_per_minute,
                60,
            )
            minute_remaining = minute_decision.remaining
            if not minute_decision.allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "type": "rate_limit_exceeded",
                            "message": "Too many requests. Per-minute limit exceeded.",
                            "details": {
                                "limit": self.requests_per_minute,
                                "window": "1 minute",
                                "retry_after": minute_decision.retry_after_seconds,
                            },
                        }
                    },
                    headers={
                        "X-RateLimit-Limit-Minute": str(self.requests_per_minute),
                        "X-RateLimit-Remaining-Minute": "0",
                        "X-RateLimit-Limit-Hour": str(self.requests_per_hour),
                        "X-RateLimit-Remaining-Hour": str(hour_remaining),
                        "Retry-After": str(minute_decision.retry_after_seconds),
                    },
                )

            hour_decision = await self.rate_limit_store.check_limit(
                tenant_id,
                self.requests_per_hour,
                3600,
            )
            hour_remaining = hour_decision.remaining
            if not hour_decision.allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": {
                            "type": "rate_limit_exceeded",
                            "message": "Too many requests. Hourly limit exceeded.",
                            "details": {
                                "limit": self.requests_per_hour,
                                "window": "1 hour",
                                "retry_after": hour_decision.retry_after_seconds,
                            },
                        }
                    },
                    headers={
                        "X-RateLimit-Limit-Minute": str(self.requests_per_minute),
                        "X-RateLimit-Remaining-Minute": str(minute_remaining),
                        "X-RateLimit-Limit-Hour": str(self.requests_per_hour),
                        "X-RateLimit-Remaining-Hour": "0",
                        "Retry-After": str(hour_decision.retry_after_seconds),
                    },
                )
        except Exception as exc:
            if self.fail_closed:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "error": {
                            "type": "rate_limit_backend_unavailable",
                            "message": f"Rate limit backend unavailable: {type(exc).__name__}",
                        }
                    },
                )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit-Minute"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, minute_remaining))
        response.headers["X-RateLimit-Limit-Hour"] = str(self.requests_per_hour)
        response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, hour_remaining))
        return response

    def _get_tenant_id(self, request: Request) -> Optional[str]:
        if hasattr(request.state, "tenant_id"):
            return request.state.tenant_id
        return request.headers.get("X-Tenant-Id") or request.headers.get("X-Tenant-ID")


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Durable idempotency middleware for mutating HTTP methods."""

    def __init__(
        self,
        app,
        *,
        idempotency_store: IdempotencyStore,
        ttl_seconds: int = 86400,
        fail_closed: bool = False,
    ):
        super().__init__(app)
        self.idempotency_store = idempotency_store
        self.ttl_seconds = ttl_seconds
        self.fail_closed = fail_closed

    async def dispatch(self, request: Request, call_next):
        if request.method not in ["POST", "PUT", "PATCH"]:
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        tenant_id = self._get_tenant_id(request)
        cache_key = build_idempotency_cache_key(
            tenant_id,
            idempotency_key,
            request.method,
            request.url.path,
        )

        try:
            acquired = await self.idempotency_store.acquire(
                cache_key=cache_key,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                request_method=request.method,
                request_path=request.url.path,
                ttl_seconds=self.ttl_seconds,
            )
        except Exception as exc:
            if self.fail_closed:
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "error": {
                            "type": "idempotency_backend_unavailable",
                            "message": f"Idempotency backend unavailable: {type(exc).__name__}",
                        }
                    },
                )
            return await call_next(request)

        if acquired.state == "replay":
            return JSONResponse(
                status_code=acquired.status_code or status.HTTP_200_OK,
                content=acquired.response_body or {},
                headers={
                    "X-Idempotency-Replay": "true",
                    "X-Idempotency-Age": str(acquired.age_seconds),
                },
            )

        if acquired.state == "in_progress":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "error": {
                        "type": "idempotency_in_progress",
                        "message": "An identical request is currently in progress",
                    }
                },
            )

        response = await call_next(request)

        if not (200 <= response.status_code < 300):
            await self.idempotency_store.release_in_progress(cache_key=cache_key)
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            payload = json.loads(body.decode())
            if isinstance(payload, dict):
                await self.idempotency_store.store_response(
                    cache_key=cache_key,
                    status_code=response.status_code,
                    response_body=payload,
                )
                return JSONResponse(
                    status_code=response.status_code,
                    content=payload,
                    headers=dict(response.headers),
                )
        except Exception:
            await self.idempotency_store.release_in_progress(cache_key=cache_key)

        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))

    def _get_tenant_id(self, request: Request) -> Optional[str]:
        if hasattr(request.state, "tenant_id"):
            return request.state.tenant_id
        return request.headers.get("X-Tenant-Id") or request.headers.get("X-Tenant-ID")


def cleanup_old_entries() -> None:
    """Compatibility no-op: cleanup is handled by durable store TTL/indexes."""
    return


# Backward compatibility symbols for legacy tests; no mutable in-memory state is used.
_rate_limit_store = None
_idempotency_store = None
