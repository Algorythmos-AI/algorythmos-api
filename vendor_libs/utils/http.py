"""Resilient HTTP client with connection pooling and retry logic."""

import asyncio
import email.utils
import random
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Awaitable, Callable

import httpx

from config import settings

# Global HTTP client for connection pooling
_client: httpx.AsyncClient | None = None

RETRIABLE_STATUS_CODES = {429, 502, 503, 504}


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse Retry-After header supporting both seconds and HTTP-date format."""
    if not header_value:
        return None
    
    try:
        # Try parsing as seconds first
        if header_value.isdigit():
            return float(header_value)
        
        # Try parsing as HTTP-date
        dt = email.utils.parsedate_to_datetime(header_value)
        return max(0.0, dt.timestamp() - time.time())
    except Exception:
        return None


async def with_retries(
    factory: Callable[[], Awaitable],
    *,
    attempts: int = 5,
    base_delay: float = 0.4,
    max_delay: float = 2.0,
    backoff_multiplier: float = 1.8
) -> any:
    """
    Retry wrapper with exponential backoff and jitter.
    
    Args:
        factory: Async function that returns the operation to retry
        attempts: Maximum number of attempts (default: 5)
        base_delay: Initial delay in seconds (default: 0.4)
        max_delay: Maximum delay cap in seconds (default: 2.0)
        backoff_multiplier: Delay multiplier for exponential backoff (default: 1.8)
    
    Returns:
        The result of the successful operation
        
    Raises:
        The last exception if all attempts fail
    """
    delay = base_delay
    last_exception = None
    
    for attempt in range(1, attempts + 1):
        try:
            return await factory()
        except httpx.HTTPStatusError as e:
            last_exception = e
            if e.response.status_code in RETRIABLE_STATUS_CODES and attempt < attempts:
                # Handle Retry-After header for 429 responses
                retry_after = _parse_retry_after(e.response.headers.get("retry-after"))
                if retry_after is not None:
                    sleep_time = min(retry_after, max_delay)
                else:
                    sleep_time = min(delay + random.random() * 0.1, max_delay)
                
                # Log retry attempt (avoid logging secrets)
                if settings.ENV in ("dev", "staging"):
                    print(f"Retry attempt {attempt}/{attempts-1} after {sleep_time:.2f}s (HTTP {e.response.status_code})")
                
                await asyncio.sleep(sleep_time)
                delay = min(delay * backoff_multiplier, max_delay)
                continue
            raise
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            last_exception = e
            if attempt < attempts:
                sleep_time = min(delay, max_delay)
                
                if settings.ENV in ("dev", "staging"):
                    print(f"Retry attempt {attempt}/{attempts-1} after {sleep_time:.2f}s ({type(e).__name__})")
                
                await asyncio.sleep(sleep_time)
                delay = min(delay * backoff_multiplier, max_delay)
                continue
            raise
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


@asynccontextmanager
async def vendor_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Get a reusable HTTP client with proper timeouts and connection pooling."""
    global _client
    
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=10.0,
                write=10.0,
                pool=10.0
            ),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=100,
                keepalive_expiry=30.0
            )
        )
    
    try:
        yield _client
    finally:
        # Keep the client alive for connection pooling
        # It will be closed on app shutdown
        pass


async def close_http_client() -> None:
    """Close the global HTTP client. Should be called on app shutdown."""
    global _client
    if _client:
        await _client.aclose()
        _client = None