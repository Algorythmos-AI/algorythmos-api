"""Distributed and durable state stores used by runtime middleware and jobs."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Literal, Optional, Protocol

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from document_processing.models import (
    BackgroundJobDB,
    IdempotencyKeyDB,
    WebhookReplayEventDB,
)

try:
    import redis.asyncio as redis_async
except Exception:  # pragma: no cover - optional dependency in local/dev edge cases
    redis_async = None


def _utcnow() -> datetime:
    return datetime.utcnow()


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of a rate-limit check/increment operation."""

    allowed: bool
    remaining: int
    retry_after_seconds: int


class RateLimitStore(Protocol):
    """Rate limit backend interface."""

    async def check_limit(self, tenant_id: str, limit: int, window_seconds: int) -> RateLimitDecision:
        ...

    async def close(self) -> None:
        ...


class InMemoryRateLimitStore:
    """Instance-scoped in-memory rate limiting store for development/testing only."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._counts: Dict[str, int] = {}
        self._expires_at: Dict[str, float] = {}

    async def check_limit(self, tenant_id: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = time.time()
        window_slot = int(now // window_seconds)
        key = f"{tenant_id}:{window_seconds}:{window_slot}"

        async with self._lock:
            self._prune(now)
            current = self._counts.get(key, 0) + 1
            self._counts[key] = current
            self._expires_at[key] = now + window_seconds

        allowed = current <= limit
        remaining = max(0, limit - current)
        retry_after = 0 if allowed else max(1, int(window_seconds - (now % window_seconds)))
        return RateLimitDecision(allowed=allowed, remaining=remaining, retry_after_seconds=retry_after)

    def _prune(self, now: float) -> None:
        stale = [key for key, expiry in self._expires_at.items() if expiry <= now]
        for key in stale:
            self._expires_at.pop(key, None)
            self._counts.pop(key, None)

    async def close(self) -> None:
        return


class RedisRateLimitStore:
    """Redis-backed distributed rate limiting store."""

    def __init__(self, redis_url: str, *, key_prefix: str = "rate_limit") -> None:
        if not redis_url:
            raise ValueError("redis_url is required")
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._client = None

    async def _get_client(self):
        if self._client is None:
            if redis_async is None:  # pragma: no cover - dependency issue
                raise RuntimeError("redis package is required for RedisRateLimitStore")
            self._client = redis_async.from_url(self._redis_url, encoding="utf-8", decode_responses=True)
        return self._client

    async def ping(self) -> None:
        client = await self._get_client()
        await client.ping()

    async def check_limit(self, tenant_id: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now_epoch = int(time.time())
        window_slot = now_epoch // window_seconds
        key = f"{self._key_prefix}:{tenant_id}:{window_seconds}:{window_slot}"

        client = await self._get_client()
        pipe = client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.ttl(key)
        current, ttl = await pipe.execute()

        current_count = int(current)
        ttl_seconds = int(ttl)
        if current_count == 1 or ttl_seconds < 0:
            await client.expire(key, window_seconds + 1)
            ttl_seconds = window_seconds

        allowed = current_count <= limit
        remaining = max(0, limit - current_count)
        retry_after = 0 if allowed else max(1, ttl_seconds)
        return RateLimitDecision(allowed=allowed, remaining=remaining, retry_after_seconds=retry_after)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()


def build_idempotency_cache_key(
    tenant_id: Optional[str],
    idempotency_key: str,
    request_method: str,
    request_path: str,
) -> str:
    """Create a stable idempotency cache key including route scope."""
    tenant_part = tenant_id or "anonymous"
    return f"{tenant_part}:{request_method.upper()}:{request_path}:{idempotency_key}"


@dataclass(frozen=True)
class IdempotencyAcquireResult:
    """Result of attempting to acquire idempotency execution ownership."""

    state: Literal["reserved", "replay", "in_progress"]
    status_code: Optional[int] = None
    response_body: Optional[dict] = None
    age_seconds: int = 0


class IdempotencyStore(Protocol):
    """Durable idempotency backend interface."""

    async def acquire(
        self,
        *,
        cache_key: str,
        tenant_id: Optional[str],
        idempotency_key: str,
        request_method: str,
        request_path: str,
        ttl_seconds: int,
    ) -> IdempotencyAcquireResult:
        ...

    async def store_response(self, *, cache_key: str, status_code: int, response_body: dict) -> None:
        ...

    async def release_in_progress(self, *, cache_key: str) -> None:
        ...


class SQLIdempotencyStore:
    """SQL-backed durable idempotency store."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def acquire(
        self,
        *,
        cache_key: str,
        tenant_id: Optional[str],
        idempotency_key: str,
        request_method: str,
        request_path: str,
        ttl_seconds: int,
    ) -> IdempotencyAcquireResult:
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)

        async with self._session_factory() as session:
            await session.execute(
                delete(IdempotencyKeyDB).where(IdempotencyKeyDB.expires_at <= now)
            )
            session.add(
                IdempotencyKeyDB(
                    cache_key=cache_key,
                    tenant_id=tenant_id,
                    request_method=request_method.upper(),
                    request_path=request_path,
                    idempotency_key=idempotency_key,
                    status_code=None,
                    response_body=None,
                    in_progress=True,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
            )
            try:
                await session.commit()
                return IdempotencyAcquireResult(state="reserved")
            except IntegrityError:
                await session.rollback()

        async with self._session_factory() as session:
            existing = await session.get(IdempotencyKeyDB, cache_key)
            if existing is None:
                return IdempotencyAcquireResult(state="in_progress")

            if existing.expires_at <= now:
                await session.delete(existing)
                await session.commit()
                return await self.acquire(
                    cache_key=cache_key,
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    request_method=request_method,
                    request_path=request_path,
                    ttl_seconds=ttl_seconds,
                )

            if (not existing.in_progress) and existing.status_code is not None and isinstance(existing.response_body, dict):
                created_at = existing.created_at or now
                age_seconds = max(0, int((now - created_at).total_seconds()))
                return IdempotencyAcquireResult(
                    state="replay",
                    status_code=int(existing.status_code),
                    response_body=existing.response_body,
                    age_seconds=age_seconds,
                )

            return IdempotencyAcquireResult(state="in_progress")

    async def store_response(self, *, cache_key: str, status_code: int, response_body: dict) -> None:
        now = _utcnow()
        async with self._session_factory() as session:
            record = await session.get(IdempotencyKeyDB, cache_key)
            if record is None:
                return
            record.status_code = status_code
            record.response_body = response_body
            record.in_progress = False
            record.updated_at = now
            await session.commit()

    async def release_in_progress(self, *, cache_key: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(IdempotencyKeyDB, cache_key)
            if record is None:
                return
            if record.in_progress:
                await session.delete(record)
                await session.commit()


class WebhookReplayStore(Protocol):
    """Store interface for webhook replay event IDs."""

    async def seen_once(self, event_id: str, ttl_seconds: int) -> bool:
        ...


class SQLWebhookReplayStore:
    """SQL-backed webhook replay protection store."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def seen_once(self, event_id: str, ttl_seconds: int) -> bool:
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)

        async with self._session_factory() as session:
            await session.execute(
                delete(WebhookReplayEventDB).where(WebhookReplayEventDB.expires_at <= now)
            )
            session.add(
                WebhookReplayEventDB(
                    event_id=event_id,
                    created_at=now,
                    expires_at=expires_at,
                )
            )
            try:
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False


class JobStore(Protocol):
    """Durable job state backend interface."""

    async def create_job(
        self,
        *,
        job_id: str,
        tenant_id: str,
        request_id: Optional[str],
        payload: dict,
        webhook_url: Optional[str],
    ) -> BackgroundJobDB:
        ...

    async def get_job(self, *, job_id: str, tenant_id: str) -> Optional[BackgroundJobDB]:
        ...

    async def mark_running(self, *, job_id: str) -> Optional[BackgroundJobDB]:
        ...

    async def mark_succeeded(
        self,
        *,
        job_id: str,
        result: dict,
        duration_sec: float,
    ) -> Optional[BackgroundJobDB]:
        ...

    async def mark_failed(
        self,
        *,
        job_id: str,
        error: str,
        duration_sec: Optional[float],
    ) -> Optional[BackgroundJobDB]:
        ...


class SQLBackgroundJobStore:
    """SQL-backed durable store for /jobs endpoint state."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_job(
        self,
        *,
        job_id: str,
        tenant_id: str,
        request_id: Optional[str],
        payload: dict,
        webhook_url: Optional[str],
    ) -> BackgroundJobDB:
        now = _utcnow()
        async with self._session_factory() as session:
            record = BackgroundJobDB(
                id=job_id,
                tenant_id=tenant_id,
                status="queued",
                request_id=request_id,
                payload=payload,
                webhook_url=webhook_url,
                result=None,
                error=None,
                duration_sec=None,
                created_at=now,
                updated_at=now,
                started_at=None,
                completed_at=None,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def get_job(self, *, job_id: str, tenant_id: str) -> Optional[BackgroundJobDB]:
        async with self._session_factory() as session:
            stmt = select(BackgroundJobDB).where(
                BackgroundJobDB.id == job_id,
                BackgroundJobDB.tenant_id == tenant_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def mark_running(self, *, job_id: str) -> Optional[BackgroundJobDB]:
        now = _utcnow()
        async with self._session_factory() as session:
            record = await session.get(BackgroundJobDB, job_id)
            if record is None:
                return None
            record.status = "running"
            record.started_at = now
            record.updated_at = now
            await session.commit()
            await session.refresh(record)
            return record

    async def mark_succeeded(
        self,
        *,
        job_id: str,
        result: dict,
        duration_sec: float,
    ) -> Optional[BackgroundJobDB]:
        now = _utcnow()
        async with self._session_factory() as session:
            record = await session.get(BackgroundJobDB, job_id)
            if record is None:
                return None
            record.status = "succeeded"
            record.result = result
            record.error = None
            record.duration_sec = duration_sec
            record.completed_at = now
            record.updated_at = now
            await session.commit()
            await session.refresh(record)
            return record

    async def mark_failed(
        self,
        *,
        job_id: str,
        error: str,
        duration_sec: Optional[float],
    ) -> Optional[BackgroundJobDB]:
        now = _utcnow()
        async with self._session_factory() as session:
            record = await session.get(BackgroundJobDB, job_id)
            if record is None:
                return None
            record.status = "failed"
            record.error = error
            record.duration_sec = duration_sec
            record.completed_at = now
            record.updated_at = now
            await session.commit()
            await session.refresh(record)
            return record


# Backward/semantic aliases for explicit interface naming.
BackgroundJobStore = JobStore
SQLJobStore = SQLBackgroundJobStore
