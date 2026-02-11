"""Tests for resilient HTTP client and vendor service retry logic."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx


@pytest.mark.asyncio
class TestRetryLogic:
    """Test the retry wrapper with various failure scenarios."""
    
    @respx.mock
    async def test_429_with_retry_after_seconds(self):
        """Test 429 response with Retry-After in seconds."""
        from vendor_libs.utils.http import with_retries, vendor_client
        
        # Mock 429 with Retry-After: 2, then success
        route = respx.get("https://test.example/endpoint").mock(
            side_effect=[
                httpx.Response(429, headers={"retry-after": "2"}),
                httpx.Response(200, json={"success": True})
            ]
        )
        
        start_time = time.time()
        
        async def request_factory():
            async with vendor_client() as client:
                response = await client.get("https://test.example/endpoint")
                response.raise_for_status()
                return response.json()
        
        result = await with_retries(request_factory, attempts=3)
        elapsed = time.time() - start_time
        
        assert result == {"success": True}
        assert route.call_count == 2
        assert elapsed >= 2.0  # Should wait at least 2 seconds for retry-after
        assert elapsed < 3.0   # But not much longer
    
    @respx.mock 
    async def test_429_with_retry_after_http_date(self):
        """Test 429 response with Retry-After as HTTP-date."""
        from vendor_libs.utils.http import with_retries, vendor_client
        import email.utils
        
        # Create HTTP-date 1 second in the future
        future_time = time.time() + 1
        http_date = email.utils.formatdate(future_time, usegmt=True)
        
        route = respx.get("https://test.example/endpoint").mock(
            side_effect=[
                httpx.Response(429, headers={"retry-after": http_date}),
                httpx.Response(200, json={"success": True})
            ]
        )
        
        start_time = time.time()
        
        async def request_factory():
            async with vendor_client() as client:
                response = await client.get("https://test.example/endpoint")
                response.raise_for_status()
                return response.json()
        
        result = await with_retries(request_factory, attempts=3)
        elapsed = time.time() - start_time
        
        assert result == {"success": True}
        assert route.call_count == 2
        assert elapsed >= 0.8  # Should wait close to 1 second
        assert elapsed < 2.0
    
    @respx.mock
    async def test_502_retry_with_backoff(self):
        """Test 502 retries with exponential backoff."""
        from vendor_libs.utils.http import with_retries, vendor_client
        
        # Mock 502 twice, then success
        route = respx.get("https://test.example/endpoint").mock(
            side_effect=[
                httpx.Response(502),
                httpx.Response(502), 
                httpx.Response(200, json={"success": True})
            ]
        )
        
        start_time = time.time()
        
        async def request_factory():
            async with vendor_client() as client:
                response = await client.get("https://test.example/endpoint")
                response.raise_for_status()
                return response.json()
        
        result = await with_retries(request_factory, attempts=5, base_delay=0.1)
        elapsed = time.time() - start_time
        
        assert result == {"success": True}
        assert route.call_count == 3
        # Should have exponential backoff: ~0.1s + ~0.18s = ~0.28s minimum
        assert elapsed >= 0.2
        assert elapsed < 1.0
    
    @respx.mock
    async def test_timeout_retry(self):
        """Test retry on timeout errors."""
        from vendor_libs.utils.http import with_retries, vendor_client
        
        call_count = 0
        
        async def request_factory():
            nonlocal call_count
            call_count += 1
            async with vendor_client() as client:
                if call_count <= 2:
                    raise httpx.ReadTimeout("Request timed out")
                response = await client.get("https://test.example/endpoint")
                response.raise_for_status()
                return response.json()
        
        # Mock successful response for final attempt
        respx.get("https://test.example/endpoint").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        
        result = await with_retries(request_factory, attempts=5, base_delay=0.05)
        
        assert result == {"success": True}
        assert call_count == 3  # 2 timeouts + 1 success
    
    @respx.mock
    async def test_non_retriable_error_no_retry(self):
        """Test that non-retriable errors (like 404) are not retried."""
        from vendor_libs.utils.http import with_retries, vendor_client
        
        route = respx.get("https://test.example/endpoint").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        
        async def request_factory():
            async with vendor_client() as client:
                response = await client.get("https://test.example/endpoint")
                response.raise_for_status()
                return response.json()
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await with_retries(request_factory, attempts=3)
        
        assert exc_info.value.response.status_code == 404
        assert route.call_count == 1  # Should not retry 404


@pytest.mark.asyncio
class TestVendorService:
    """Test the vendor service with retry integration."""
    
    @respx.mock
    async def test_vendor_health_check_success(self):
        """Test successful vendor health check."""
        from vendor_libs.services.vendor import VendorService
        
        vendor = VendorService("https://api.vendor.example")
        
        respx.get("https://api.vendor.example/health").mock(
            return_value=httpx.Response(200)
        )
        
        result = await vendor.vendor_health_check()
        assert result is True
    
    @respx.mock
    async def test_vendor_health_check_failure(self):
        """Test vendor health check with failure."""
        from vendor_libs.services.vendor import VendorService
        
        vendor = VendorService("https://api.vendor.example")
        
        respx.get("https://api.vendor.example/health").mock(
            return_value=httpx.Response(503)
        )
        
        result = await vendor.vendor_health_check()
        assert result is False
    
    @respx.mock
    async def test_upload_files_with_retry(self):
        """Test file upload with automatic retry on failure."""
        from vendor_libs.services.vendor import VendorService
        
        vendor = VendorService("https://api.vendor.example")
        
        # Mock 503 then success
        route = respx.post("https://api.vendor.example/upload").mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"upload_id": "123", "status": "uploaded"})
            ]
        )
        
        files = [{"name": "test.pdf", "size": 1024}]
        result = await vendor.upload_files(files, tenant_id="test-tenant")
        
        assert result == {"upload_id": "123", "status": "uploaded"}
        assert route.call_count == 2
        
        # Check that tenant header was sent
        last_request = route.calls[-1].request
        assert last_request.headers["X-Tenant-ID"] == "test-tenant"
    
    @respx.mock
    async def test_create_job_with_retry(self):
        """Test job creation with retry on network error."""
        from vendor_libs.services.vendor import VendorService
        
        vendor = VendorService("https://api.vendor.example")
        
        call_count = 0
        
        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectTimeout("Connection timeout")
            return httpx.Response(200, json={"job_id": "job-123", "status": "created"})
        
        respx.post("https://api.vendor.example/jobs").mock(side_effect=side_effect)
        
        job_data = {"input": "test.pdf", "processor": "pdf-extractor"}
        result = await vendor.create_job(job_data)
        
        assert result == {"job_id": "job-123", "status": "created"}
        assert call_count == 2  # One timeout, one success


@pytest.mark.asyncio
class TestResilientHttpClient:
    """Test the resilient HTTP client functionality."""
    
    async def test_client_reuse(self):
        """Test that the HTTP client is reused across requests."""
        from vendor_libs.utils.http import vendor_client
        
        client1_id = None
        client2_id = None
        
        async with vendor_client() as client1:
            client1_id = id(client1)
        
        async with vendor_client() as client2:
            client2_id = id(client2)
        
        # Should be the same client instance (connection pooling)
        assert client1_id == client2_id
    
    async def test_close_http_client(self):
        """Test that the HTTP client can be properly closed."""
        from vendor_libs.utils.http import vendor_client, close_http_client, _client
        
        # Use the client to initialize it
        async with vendor_client() as client:
            assert client is not None
        
        # Client should exist after use
        assert _client is not None
        
        # Close the client
        await close_http_client()
        
        # Client should be None after closing
        from vendor_libs.utils import http
        assert http._client is None