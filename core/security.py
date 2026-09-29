"""Credential and outbound-URL checks shared by route dependencies and middleware.

Kept outside the ``app`` package on purpose: importing ``app`` loads the whole
application, which the middleware modules must not do.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlsplit

from starlette.requests import Request


def secure_equals(presented: str, expected: str) -> bool:
    """Compare two secrets in constant time."""
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    """Return the token from an ``Authorization: Bearer <token>`` header, else None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def matching_static_credential(request: Request, configured_key: Optional[str]) -> Optional[str]:
    """Return the presented credential that equals the configured static key, else None.

    The Bearer token is checked first. A Bearer token that does not match falls
    through to ``X-API-Key``, so a caller sending a sign-in token alongside a
    valid key is not rejected.
    """
    expected = (configured_key or "").strip()
    if not expected:
        return None
    candidates = (
        bearer_token(request.headers.get("authorization")),
        request.headers.get("x-api-key"),
    )
    for candidate in candidates:
        if candidate and secure_equals(candidate, expected):
            return candidate
    return None


def credential_fingerprint(credential: str) -> str:
    """Stable, non-reversible identifier for a credential (safe to use in cache keys)."""
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()[:32]


class UnsafeOutboundURL(ValueError):
    """Raised when an outbound URL could reach a private or internal address."""


def assert_public_https_url(url: str) -> None:
    """Refuse outbound calls that are not HTTPS or that resolve to a non-public address.

    Every address the host resolves to must be globally routable, so loopback,
    private, link-local (cloud metadata), reserved and multicast targets are
    rejected. Call it both when a URL is accepted and again right before the
    request is sent, because DNS can change in between.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise UnsafeOutboundURL("webhook_url must use https")
    host = parts.hostname
    if not host:
        raise UnsafeOutboundURL("webhook_url has no host")
    try:
        infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeOutboundURL("webhook_url host does not resolve") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise UnsafeOutboundURL("webhook_url host does not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeOutboundURL("webhook_url resolves to a non-public address")
