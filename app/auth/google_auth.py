"""Google OAuth2 token verification service.

This module provides secure verification of Google ID tokens using
Google's official `google-auth` library. The verification process:

1. Fetches Google's public keys (automatically cached by the library)
2. Verifies the token signature cryptographically
3. Validates issuer, audience (if configured), and expiry claims
4. Extracts user information (email, name, picture, sub)

Security notes:
- Tokens are NEVER logged
- Only verified email addresses are accepted
- Issuer is validated against Google's domains
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


@dataclass
class GoogleUserInfo:
    """Verified user information from Google ID token.
    
    Attributes:
        email: The user's verified email address
        name: Display name (may be None)
        picture: Avatar URL (may be None)
        sub: Google's unique account ID (stable, never changes)
    """
    email: str
    name: Optional[str]
    picture: Optional[str]
    sub: str


class GoogleAuthError(Exception):
    """Raised when Google token verification fails.
    
    This exception is raised for any authentication failure including:
    - Invalid token signature
    - Expired token
    - Invalid issuer
    - Unverified email
    - Network errors fetching Google's public keys
    
    The error message intentionally does not expose token details.
    """
    pass


def verify_google_token(token: str, client_id: Optional[str] = None) -> GoogleUserInfo:
    """
    Verify a Google ID token and extract user information.
    
    This function uses Google's official verification library which:
    - Automatically fetches and caches Google's public keys
    - Verifies token signature cryptographically
    - Validates standard claims (iss, exp, iat)
    
    Args:
        token: The Google ID token from the frontend (JWT format)
        client_id: Optional Google OAuth client ID for audience validation.
                   If None, audience validation is skipped (useful for development).
                   In production, this should be set for security.
        
    Returns:
        GoogleUserInfo with verified user data
        
    Raises:
        GoogleAuthError: If token is invalid, expired, or verification fails
    """
    try:
        # Use Google's official verification
        # The Request() object handles HTTP transport for fetching public keys
        id_info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=client_id,  # None = skip audience check
        )
        
        # Validate issuer is from Google
        issuer = id_info.get("iss")
        if issuer not in ("accounts.google.com", "https://accounts.google.com"):
            raise GoogleAuthError("Invalid token issuer")
        
        # Validate email is verified by Google
        # This prevents accepting tokens from unverified Google accounts
        if not id_info.get("email_verified", False):
            raise GoogleAuthError("Email not verified by Google")
        
        # Extract required email
        email = id_info.get("email")
        if not email:
            raise GoogleAuthError("No email in token")
        
        # Extract Google's unique user ID (sub claim)
        sub = id_info.get("sub")
        if not sub:
            raise GoogleAuthError("No sub claim in token")
        
        return GoogleUserInfo(
            email=email,
            name=id_info.get("name"),
            picture=id_info.get("picture"),
            sub=sub,
        )
        
    except ValueError as e:
        # Token verification failed (expired, invalid signature, malformed, etc.)
        raise GoogleAuthError(f"Token verification failed: {e}") from e
    except GoogleAuthError:
        # Re-raise our own errors as-is
        raise
    except Exception as e:
        # Catch-all for unexpected errors (network issues fetching keys, etc.)
        raise GoogleAuthError(f"Authentication error: {type(e).__name__}") from e
