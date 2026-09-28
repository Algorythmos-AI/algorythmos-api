"""Resolve per-user credentials to a user and the tenant they act for.

Two credential types map to a user: per-user ``alg_`` API keys (stored as
SHA-256 hashes) and Google ID tokens. Tenants are assigned lazily: a user or
key created before tenant binding gets its tenant the next time it is used,
so no data migration is needed.

Kept outside the ``app`` package so it can be imported without loading the
whole application; the Google verifier is imported when a request needs it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import uuid4

from sqlalchemy import select

from core.tenancy import google_tenant_for

API_KEY_PREFIX = "alg_"


def hash_api_key(raw_key: str) -> str:
    """SHA-256 of a raw API key; only the hash is stored."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def ensure_user_tenant(settings, user: Any) -> str:
    """Return the user's tenant, assigning it on first use."""
    if not user.tenant_id:
        user.tenant_id = google_tenant_for(settings, user.email or "", user.id)
    return user.tenant_id


async def user_and_tenant_from_api_key(raw_key: Optional[str], session, settings) -> Optional[tuple[Any, str]]:
    """Look up an active ``alg_`` key and its active user; return (user, tenant) or None."""
    if not raw_key or not raw_key.startswith(API_KEY_PREFIX):
        return None

    from models_api_key import ApiKeyDB
    from models_user import UserDB

    key = (
        await session.execute(
            select(ApiKeyDB).where(ApiKeyDB.key_hash == hash_api_key(raw_key), ApiKeyDB.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if key is None:
        return None

    user = (
        await session.execute(select(UserDB).where(UserDB.id == key.user_id, UserDB.is_active.is_(True)))
    ).scalar_one_or_none()
    if user is None:
        return None

    # The key's own tenant is authoritative; older keys inherit the user's tenant.
    if not key.tenant_id:
        key.tenant_id = ensure_user_tenant(settings, user)
    key.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return user, key.tenant_id


async def user_from_google_token(
    token: Optional[str],
    session,
    settings,
    is_allowed: Callable[[Optional[str]], bool],
) -> Optional[Any]:
    """Verify a Google ID token and return the (possibly new) allow-listed user, else None."""
    if not token:
        return None

    from app.auth.google_auth import GoogleAuthError, verify_google_token
    from models_user import UserDB

    try:
        info = verify_google_token(token, client_id=settings.GOOGLE_CLIENT_ID)
    except GoogleAuthError:
        return None

    if not is_allowed(info.email):
        return None

    user = (
        await session.execute(select(UserDB).where(UserDB.email == info.email, UserDB.is_active.is_(True)))
    ).scalar_one_or_none()

    if user is None:
        user = UserDB(
            id=str(uuid4()),
            email=info.email,
            display_name=getattr(info, "name", None),
            avatar_url=getattr(info, "picture", None),
            provider="google",
            provider_account_id=getattr(info, "sub", None),
        )
        session.add(user)

    ensure_user_tenant(settings, user)
    await session.commit()
    await session.refresh(user)
    return user
