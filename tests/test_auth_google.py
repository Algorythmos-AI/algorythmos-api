"""
Tests for POST /api/auth/google endpoint.

These tests mock Google token verification to avoid external calls.
The endpoint uses Google Identity Services (GIS) with ID tokens,
NOT OAuth redirect flow.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest


class TestAuthGoogle:
    """Tests for Google authentication endpoint."""

    @pytest.mark.asyncio
    async def test_auth_google_success(self, app_client):
        """Test successful Google token verification creates user."""
        mock_user_info = MagicMock()
        mock_user_info.email = "test@example.com"
        mock_user_info.name = "Test User"
        mock_user_info.picture = "https://example.com/avatar.jpg"
        mock_user_info.sub = "google-user-id-12345"
        
        with patch("app.auth.google_auth.verify_google_token") as mock_verify:
            mock_verify.return_value = mock_user_info
            
            response = await app_client.post(
                "/auth/google",
                headers={"Authorization": "Bearer fake-google-token"}
            )
            
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            mock_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_google_invalid_token(self, app_client):
        """Test invalid token returns 401."""
        from app.auth.google_auth import GoogleAuthError
        
        with patch("app.auth.google_auth.verify_google_token") as mock_verify:
            mock_verify.side_effect = GoogleAuthError("Invalid token")
            
            response = await app_client.post(
                "/auth/google",
                headers={"Authorization": "Bearer invalid-token"}
            )
            
            assert response.status_code == 401
            assert response.json()["code"] == "INVALID_TOKEN"

    @pytest.mark.asyncio
    async def test_auth_google_missing_bearer(self, app_client):
        """Test missing Bearer prefix returns 401."""
        response = await app_client.post(
            "/auth/google",
            headers={"Authorization": "not-a-bearer-token"}
        )
        
        assert response.status_code == 401
        assert response.json()["code"] == "INVALID_AUTH_HEADER"

    @pytest.mark.asyncio
    async def test_auth_google_missing_header(self, app_client):
        """Test missing Authorization header returns 422."""
        response = await app_client.post("/auth/google")
        
        # FastAPI returns 422 for missing required header
        assert response.status_code == 422
