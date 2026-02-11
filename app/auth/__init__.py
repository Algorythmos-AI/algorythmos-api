"""Authentication services package.

This package contains authentication-related services for the Algorythmos API.
Currently supports:
- Google OAuth2 token verification

Future support planned for:
- Enterprise SSO (SAML/OIDC)
- API key ownership verification
"""

from __future__ import annotations

from app.auth.google_auth import verify_google_token, GoogleAuthError, GoogleUserInfo

__all__ = ["verify_google_token", "GoogleAuthError", "GoogleUserInfo"]
