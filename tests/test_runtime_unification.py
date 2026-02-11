"""Runtime unification and deploy entrypoint parity tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import app as canonical_runtime
import service
from api import index as serverless_index


@pytest.mark.asyncio
async def test_deploy_entrypoints_resolve_same_canonical_app() -> None:
    """Docker/service and serverless entrypoints must expose the same app object."""
    canonical_app = canonical_runtime.app

    assert service.app is canonical_app
    assert serverless_index.app is canonical_app

    entry_module = getattr(canonical_runtime, "_app_entry")
    assert canonical_app is entry_module.app
    assert Path(entry_module.__file__).name == "app.py"


@pytest.mark.asyncio
async def test_service_shim_auth_behavior_matches_canonical_runtime() -> None:
    """Compatibility shim must not diverge from canonical auth behavior."""

    async def _request(test_app):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/extract/path",
                headers={"X-Tenant-ID": "tenant-runtime-parity"},
                json={"input_path": "/tmp/does-not-matter"},
            )

    canonical_response = await _request(canonical_runtime.app)
    shim_response = await _request(service.app)

    assert canonical_response.status_code == 401
    assert shim_response.status_code == canonical_response.status_code
    assert shim_response.json() == canonical_response.json()


def test_startup_security_validation_requires_api_key_in_production(monkeypatch) -> None:
    """Production startup must fail fast when ALG_API_KEY is unset."""
    import app_main

    monkeypatch.setattr(app_main.settings, "ENV", "production")
    monkeypatch.setattr(app_main.settings, "ALG_API_KEY", "")
    monkeypatch.setattr(app_main.settings, "GOOGLE_CLIENT_ID", "configured-client-id")

    with pytest.raises(RuntimeError, match="ALG_API_KEY"):
        app_main._validate_startup_security_configuration()


def test_startup_security_validation_requires_google_client_id_in_production(monkeypatch) -> None:
    """Production startup must fail fast when GOOGLE_CLIENT_ID is unset."""
    import app_main

    monkeypatch.setattr(app_main.settings, "ENV", "production")
    monkeypatch.setattr(app_main.settings, "ALG_API_KEY", "configured-api-key")
    monkeypatch.setattr(app_main.settings, "GOOGLE_CLIENT_ID", None)

    with pytest.raises(RuntimeError, match="GOOGLE_CLIENT_ID"):
        app_main._validate_startup_security_configuration()
