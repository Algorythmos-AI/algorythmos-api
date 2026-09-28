"""Tenant binding rules: which tenant a credential may act for.

The tenant comes from the credential, never from the caller alone:

* the static key acts for ``ALG_TENANT_ID`` (plus any tenants listed in the
  deprecated ``ALG_STATIC_KEY_ALLOWED_TENANTS``);
* a per-user ``alg_`` key acts for the tenant stored on the key;
* a Google-authenticated user acts for the tenant stored on the user, assigned
  from ``GOOGLE_TENANT_MAP`` (domain -> tenant) or a per-user tenant.

An ``X-Tenant-Id`` header is optional. When present it must equal the bound
tenant, otherwise the request is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

WILDCARD = "*"


class TenantMismatch(Exception):
    """The requested tenant is not one this credential may act for."""


class TenantUnresolved(Exception):
    """No tenant could be determined for this credential."""


def _csv(value: Optional[str]) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


@dataclass(frozen=True)
class StaticKeyTenants:
    default: Optional[str]
    allowed: frozenset[str]
    any_tenant: bool

    @classmethod
    def from_settings(cls, settings) -> "StaticKeyTenants":
        default = (settings.ALG_TENANT_ID or "").strip() or None
        extra = _csv(getattr(settings, "ALG_STATIC_KEY_ALLOWED_TENANTS", ""))
        allowed = frozenset(({default} if default else set()) | (extra - {WILDCARD}))
        return cls(default=default, allowed=allowed, any_tenant=WILDCARD in extra)


def static_key_tenant(settings, requested: Optional[str]) -> str:
    """Tenant the static key acts for, given an optional requested tenant."""
    rules = StaticKeyTenants.from_settings(settings)
    requested = (requested or "").strip() or None
    if requested is None:
        if rules.default is None:
            raise TenantUnresolved("Missing X-Tenant-ID header")
        return rules.default
    if rules.any_tenant or requested in rules.allowed:
        return requested
    raise TenantMismatch(requested)


def static_key_tenant_or_none(settings, requested: Optional[str]) -> Optional[str]:
    """Non-raising variant for middleware: None when the route will refuse the request."""
    try:
        return static_key_tenant(settings, requested)
    except (TenantMismatch, TenantUnresolved):
        return None


def bound_tenant(bound: Optional[str], requested: Optional[str]) -> str:
    """Tenant for a user or per-user key principal whose tenant is stored with it."""
    if not bound:
        raise TenantUnresolved("Credential has no tenant")
    requested = (requested or "").strip() or None
    if requested is not None and requested != bound:
        raise TenantMismatch(requested)
    return bound


def google_tenant_for(settings, email: str, user_id: str) -> str:
    """Tenant assigned to a Google user on first sign-in.

    ``GOOGLE_TENANT_MAP`` maps email domains to shared tenants
    (``example.com=acme,example.org=acme``). Anyone else gets a tenant of their
    own, so users of a public mail domain never share one.
    """
    mapping: dict[str, str] = {}
    for pair in _csv(getattr(settings, "GOOGLE_TENANT_MAP", "")):
        domain, sep, tenant = pair.partition("=")
        if sep and domain.strip() and tenant.strip():
            mapping[domain.strip().lower().lstrip("@")] = tenant.strip()
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    return mapping.get(domain) or f"user-{user_id}"
