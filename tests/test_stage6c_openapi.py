import importlib.util
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


def _load_app_module():
    root = Path(__file__).resolve().parents[1]
    module_name = "app_main_stage6c"
    spec = importlib.util.spec_from_file_location(module_name, root / "app.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


app_module = _load_app_module()
app = app_module.app


async def _load_openapi(client: AsyncClient) -> dict:
    for path in ("/openapi.json", "/api/openapi.json"):
        response = await client.get(path)
        if response.status_code == 200:
            return response.json()
    pytest.fail("OpenAPI document not accessible at /openapi.json or /api/openapi.json")


@pytest.mark.asyncio
async def test_openapi_tags_and_deprecations():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        doc = await _load_openapi(client)

    paths = doc.get("paths", {})
    assert paths, "OpenAPI paths missing"

    seen_tags = set()
    deprecated_found = False
    for methods in paths.values():
        for op in methods.values():
            if not isinstance(op, dict):
                continue
            for tag in op.get("tags") or []:
                seen_tags.add(tag)
            if op.get("deprecated"):
                deprecated_found = True

    for expected in {"health", "processors", "runs", "webhooks", "legacy"}:
        assert expected in seen_tags, f"Missing tag {expected}"
    assert deprecated_found, "Expected at least one deprecated legacy operation"


@pytest.mark.asyncio
async def test_run_endpoints_include_examples():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        doc = await _load_openapi(client)

    paths = doc.get("paths", {})
    found_get_examples = False
    found_post_examples = False

    for path, methods in paths.items():
        if "{processor" in path and "runs" in path:
            get_op = methods.get("get")
            post_op = methods.get("post")

            if get_op:
                content = (((get_op.get("responses") or {}).get("200") or {}).get("content") or {})
                for media in content.values():
                    examples = media.get("examples") or {}
                    if any(key in examples for key in ("extract", "failed")):
                        found_get_examples = True

            if post_op and "runs" in (post_op.get("tags") or []):
                content = (((post_op.get("responses") or {}).get("200") or {}).get("content") or {})
                for media in content.values():
                    examples = media.get("examples") or {}
                    if "queued" in examples:
                        found_post_examples = True

    assert found_get_examples, "GET run endpoint examples missing"
    assert found_post_examples, "POST run endpoint examples missing"
