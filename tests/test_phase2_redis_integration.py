"""Integration checks for Redis-backed distributed runtime state."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from document_processing.state import RedisRateLimitStore


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_rate_limit_is_shared_across_store_instances():
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL not configured for integration test")

    tenant_id = f"tenant-{uuid4().hex[:8]}"
    key_prefix = f"phase2-it-{uuid4().hex[:8]}"
    limit = 2

    store_a = RedisRateLimitStore(redis_url, key_prefix=key_prefix)
    store_b = RedisRateLimitStore(redis_url, key_prefix=key_prefix)

    try:
        first = await store_a.check_limit(tenant_id, limit, 60)
        second = await store_b.check_limit(tenant_id, limit, 60)
        third = await store_a.check_limit(tenant_id, limit, 60)
    finally:
        await store_a.close()
        await store_b.close()

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.retry_after_seconds >= 1
