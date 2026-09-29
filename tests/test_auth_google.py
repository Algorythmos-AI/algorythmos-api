"""Authentication hardening tests for Google auth and protected routes."""

from __future__ import annotations

import os

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.auth.google_auth import GoogleAuthError
from config import settings


async def _post_with_api_prefix_fallback(app_client, path: str, **kwargs):
    response = await app_client.post(path, **kwargs)
    if response.status_code == 404 and not path.startswith("/api/"):
        return await app_client.post(f"/api{path}", **kwargs)
    return response


@pytest.mark.asyncio
async def test_auth_google_success(app_client):
    """Valid Google token is accepted when verification passes."""
    with patch("app.auth.google_auth.verify_google_token") as mock_verify:
        mock_verify.return_value = SimpleNamespace(
            email="test@example.com",
            name="Test User",
            picture="https://example.com/avatar.jpg",
            sub="google-user-id-12345",
        )

        response = await _post_with_api_prefix_fallback(
            app_client,
            "/auth/google",
            headers={"Authorization": "Bearer fake-google-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_verify.assert_called_once_with(
        "fake-google-token",
        client_id=settings.GOOGLE_CLIENT_ID,
    )


@pytest.mark.asyncio
async def test_auth_google_invalid_token_returns_401(app_client):
    """Invalid Google token should be rejected."""
    with patch("app.auth.google_auth.verify_google_token") as mock_verify:
        mock_verify.side_effect = GoogleAuthError("Invalid token")
        response = await _post_with_api_prefix_fallback(
            app_client,
            "/auth/google",
            headers={"Authorization": "Bearer invalid-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_auth_google_missing_client_id_audience_returns_401(app_client, monkeypatch):
    """Missing Google client ID config should reject auth (no audience skipping)."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", None)
    response = await _post_with_api_prefix_fallback(
        app_client,
        "/auth/google",
        headers={"Authorization": "Bearer token-without-audience-check"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_auth_google_incorrect_audience_returns_401(app_client):
    """Incorrect audience should be rejected."""
    with patch("app.auth.google_auth.verify_google_token") as mock_verify:
        mock_verify.side_effect = GoogleAuthError("Wrong audience")
        response = await _post_with_api_prefix_fallback(
            app_client,
            "/auth/google",
            headers={"Authorization": "Bearer wrong-audience-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_protected_route_without_valid_auth_is_rejected(app_client):
    """Protected routes must reject unauthenticated requests."""
    response = await _post_with_api_prefix_fallback(
        app_client,
        "/extract/path",
        headers={"X-Tenant-ID": "tenant-auth-test"},
        json={"input_path": "/tmp/does-not-matter"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_with_valid_auth_still_works(app_client):
    """Valid static auth can access route logic beyond auth checks."""
    response = await _post_with_api_prefix_fallback(
        app_client,
        "/extract/path",
        headers={
            "X-API-Key": settings.ALG_API_KEY,
            "X-Tenant-ID": "tenant-auth-test",
        },
        # Missing path inside the allowed base directory (see conftest), so the
        # request passes auth and the path guard and fails on existence.
        json={"input_path": os.path.join(os.environ["LOCAL_EXTRACT_BASE_DIR"], "definitely-missing-path")},
    )

    # Valid auth reaches business logic and fails on path validation, not auth.
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PATH_NOT_FOUND"
