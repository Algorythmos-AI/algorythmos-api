import datetime
import email.utils
from io import BytesIO

import pytest
import httpx
from httpx import Response
from types import SimpleNamespace

from vendor_libs.services import vendor as vendor_services
from tests.conftest import TEST_VENDOR_BASE


pytestmark = pytest.mark.asyncio


def _make_upload(payload: bytes | BytesIO = b"%PDF-1.4\n") -> SimpleNamespace:
    if isinstance(payload, BytesIO):
        data = payload.getvalue()
    else:
        data = payload

    file_obj = BytesIO(data)

    def _read(size: int = -1) -> bytes:
        return file_obj.read(size)

    def _seek(offset: int, whence: int = 0) -> int:
        return file_obj.seek(offset, whence)

    return SimpleNamespace(
        filename="retry.pdf",
        content_type="application/pdf",
        read=_read,
        seek=_seek,
        file=file_obj,
    )


async def test_429_retry_after_seconds_respected(fake_vendor, fast_sleep):
    route = fake_vendor.post(f"{TEST_VENDOR_BASE}/extract/upload")
    route.side_effect = [
        Response(429, headers={"Retry-After": "2"}),
        Response(200, json={"input_path": "vendor://429-seconds"}),
    ]

    result = await vendor_services.upload_files_stream([_make_upload()])

    assert result["input_path"] == "vendor://429-seconds"
    assert route.call_count == 2
    assert fast_sleep["durations"], "Expected retry sleep to be recorded"
    assert fast_sleep["durations"][0] >= 2.0 - 1e-6


async def test_429_retry_after_http_date(fake_vendor, fast_sleep):
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=3)
    http_date = email.utils.format_datetime(dt, usegmt=True)

    route = fake_vendor.post(f"{TEST_VENDOR_BASE}/extract/upload")
    route.side_effect = [
        Response(429, headers={"Retry-After": http_date}),
        Response(200, json={"input_path": "vendor://429-date"}),
    ]

    result = await vendor_services.upload_files_stream([_make_upload()])

    assert result["input_path"] == "vendor://429-date"
    assert route.call_count == 2
    assert fast_sleep["durations"], "Expected retry sleep to be recorded"


async def test_502_backoff_then_success(fake_vendor, fast_sleep):
    route = fake_vendor.post(f"{TEST_VENDOR_BASE}/extract/upload")
    route.side_effect = [
        Response(502),
        Response(502),
        Response(200, json={"input_path": "vendor://502"}),
    ]

    result = await vendor_services.upload_files_stream([_make_upload()])

    assert result["input_path"] == "vendor://502"
    sleeps = fast_sleep["durations"]
    assert len(sleeps) >= 2
    assert sleeps[0] > 0
    assert sleeps[1] >= sleeps[0]


async def test_404_non_retriable(fake_vendor, fast_sleep):
    route = fake_vendor.post(f"{TEST_VENDOR_BASE}/extract/upload").mock(
        return_value=Response(404)
    )

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await vendor_services.upload_files_stream([_make_upload()])

    assert exc_info.value.response.status_code == 404
    assert fast_sleep["durations"] == []
    assert route.call_count == 1
