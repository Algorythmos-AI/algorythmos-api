"""Tenant binding: the tenant comes from the credential, never from the caller alone.

Requests go to ``/extract/path`` with a missing path inside the allowed base
directory. That endpoint needs no database, so the response code shows exactly
how far a request got:

* ``400 PATH_NOT_FOUND``  -> authenticated and bound to a tenant
* ``400 MISSING_TENANT``  -> authenticated, no tenant could be determined
* ``403 TENANT_MISMATCH`` -> authenticated, but not for the requested tenant
* ``401``                 -> not authenticated
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from core.principals import hash_api_key
from core.tenancy import (
    TenantMismatch,
    TenantUnresolved,
    bound_tenant,
    google_tenant_for,
    static_key_tenant,
)
from models_api_key import ApiKeyDB
from models_user import UserDB

app_main = sys.modules["app_main"]
MISSING = str(Path(os.environ["LOCAL_EXTRACT_BASE_DIR"]) / f"alg-tenant-missing-{os.getpid()}")


async def _call(client: AsyncClient, headers: dict[str, str]):
    response = await client.post("/extract/path", headers=headers, json={"input_path": MISSING})
    detail = response.json().get("detail")
    code = detail.get("code") if isinstance(detail, dict) else None
    return response.status_code, code


@pytest.fixture
def strict_static(monkeypatch):
    """Production-like rules: the static key acts for tenant-a only."""
    monkeypatch.setattr(settings, "ALG_STATIC_KEY_ALLOWED_TENANTS", "")
    monkeypatch.setattr(settings, "ALG_TENANT_ID", "tenant-a")


@pytest.fixture
async def tenant_db(tmp_path):
    """Isolated users/api_keys database wired into the app's session dependencies."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'tenancy.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: UserDB.metadata.create_all(c, tables=[UserDB.__table__, ApiKeyDB.__table__])
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _session():
        async with factory() as session:
            yield session

    app = app_main.app
    overrides = {app_main._db_session: _session, app_main.get_session: _session}
    app.dependency_overrides.update(overrides)
    try:
        yield factory
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)
        await engine.dispose()


async def _seed_user_and_key(factory, *, email: str, key_active: bool = True) -> tuple[str, str]:
    raw = f"alg_{uuid4().hex}"
    user_id = str(uuid4())
    async with factory() as session:
        session.add(UserDB(id=user_id, email=email, provider="google"))
        session.add(
            ApiKeyDB(
                id=str(uuid4()),
                user_id=user_id,
                name="test",
                key_hash=hash_api_key(raw),
                prefix=raw[:12],
                is_active=key_active,
            )
        )
        await session.commit()
    return user_id, raw


# --- rules (unit) ------------------------------------------------------------------


def test_static_key_rules() -> None:
    rules = SimpleNamespace(ALG_TENANT_ID="tenant-a", ALG_STATIC_KEY_ALLOWED_TENANTS="tenant-b")
    assert static_key_tenant(rules, None) == "tenant-a"
    assert static_key_tenant(rules, "tenant-a") == "tenant-a"
    assert static_key_tenant(rules, "tenant-b") == "tenant-b"
    with pytest.raises(TenantMismatch):
        static_key_tenant(rules, "tenant-c")
    with pytest.raises(TenantUnresolved):
        static_key_tenant(SimpleNamespace(ALG_TENANT_ID=None, ALG_STATIC_KEY_ALLOWED_TENANTS=""), None)
    anything = SimpleNamespace(ALG_TENANT_ID=None, ALG_STATIC_KEY_ALLOWED_TENANTS="*")
    assert static_key_tenant(anything, "whatever") == "whatever"


def test_bound_tenant_and_google_assignment() -> None:
    assert bound_tenant("t1", None) == "t1"
    assert bound_tenant("t1", "t1") == "t1"
    with pytest.raises(TenantMismatch):
        bound_tenant("t1", "t2")
    with pytest.raises(TenantUnresolved):
        bound_tenant(None, None)

    rules = SimpleNamespace(GOOGLE_TENANT_MAP="algorythmos.com.au=algorythmos, @partner.org=partner")
    assert google_tenant_for(rules, "a@algorythmos.com.au", "u1") == "algorythmos"
    assert google_tenant_for(rules, "b@Partner.org", "u2") == "partner"
    # Public mail domains never share a tenant.
    assert google_tenant_for(rules, "x@gmail.com", "u3") == "user-u3"
    assert google_tenant_for(rules, "y@gmail.com", "u4") == "user-u4"


# --- static key ----------------------------------------------------------------------


async def test_static_key_binds_to_configured_tenant(app_client: AsyncClient, strict_static) -> None:
    key = {"X-API-Key": settings.ALG_API_KEY}
    assert await _call(app_client, key) == (400, "PATH_NOT_FOUND")
    assert await _call(app_client, {**key, "X-Tenant-Id": "tenant-a"}) == (400, "PATH_NOT_FOUND")
    assert await _call(app_client, {**key, "X-Tenant-Id": "tenant-b"}) == (403, "TENANT_MISMATCH")


async def test_static_key_allowed_tenant_list(app_client: AsyncClient, strict_static, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ALG_STATIC_KEY_ALLOWED_TENANTS", "tenant-b")
    key = {"X-API-Key": settings.ALG_API_KEY}
    assert await _call(app_client, {**key, "X-Tenant-Id": "tenant-b"}) == (400, "PATH_NOT_FOUND")
    assert await _call(app_client, {**key, "X-Tenant-Id": "tenant-c"}) == (403, "TENANT_MISMATCH")


async def test_static_key_without_any_tenant(app_client: AsyncClient, strict_static, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ALG_TENANT_ID", None)
    assert await _call(app_client, {"X-API-Key": settings.ALG_API_KEY}) == (400, "MISSING_TENANT")


async def test_mismatched_tenant_is_not_counted_or_cached(app_client: AsyncClient, strict_static) -> None:
    headers = {"X-API-Key": settings.ALG_API_KEY, "X-Tenant-Id": "tenant-b", "Idempotency-Key": "tb-1"}
    for _ in range(3):
        assert await _call(app_client, headers) == (403, "TENANT_MISMATCH")


# --- per-user alg_ keys ------------------------------------------------------------------


async def test_user_api_key_binds_to_its_tenant(app_client: AsyncClient, tenant_db, strict_static) -> None:
    user_id, raw = await _seed_user_and_key(tenant_db, email="dev@gmail.com")

    assert await _call(app_client, {"X-API-Key": raw}) == (400, "PATH_NOT_FOUND")
    assert await _call(app_client, {"Authorization": f"Bearer {raw}"}) == (400, "PATH_NOT_FOUND")
    assert await _call(app_client, {"X-API-Key": raw, "X-Tenant-Id": f"user-{user_id}"}) == (400, "PATH_NOT_FOUND")
    assert await _call(app_client, {"X-API-Key": raw, "X-Tenant-Id": "tenant-a"}) == (403, "TENANT_MISMATCH")

    # The tenant was assigned lazily and stored on both the user and the key.
    async with tenant_db() as session:
        user = (await session.execute(select(UserDB).where(UserDB.id == user_id))).scalar_one()
        key = (await session.execute(select(ApiKeyDB).where(ApiKeyDB.user_id == user_id))).scalar_one()
    assert user.tenant_id == f"user-{user_id}"
    assert key.tenant_id == user.tenant_id
    assert key.last_used_at is not None


async def test_inactive_or_unknown_user_key_rejected(app_client: AsyncClient, tenant_db, strict_static) -> None:
    _, raw = await _seed_user_and_key(tenant_db, email="old@gmail.com", key_active=False)
    assert (await _call(app_client, {"X-API-Key": raw}))[0] == 401
    assert (await _call(app_client, {"X-API-Key": "alg_does-not-exist"}))[0] == 401


# --- Google users -----------------------------------------------------------------------


def _google(email: str):
    return SimpleNamespace(email=email, name="Test", picture=None, sub=uuid4().hex)


async def test_google_user_binds_to_mapped_or_own_tenant(
    app_client: AsyncClient, tenant_db, strict_static, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", "algorythmos.com.au,gmail.com")
    monkeypatch.setattr(settings, "GOOGLE_TENANT_MAP", "algorythmos.com.au=algorythmos")
    bearer = {"Authorization": "Bearer google-id-token"}

    with patch("app.auth.google_auth.verify_google_token", return_value=_google("sam@algorythmos.com.au")):
        assert await _call(app_client, bearer) == (400, "PATH_NOT_FOUND")
        assert await _call(app_client, {**bearer, "X-Tenant-Id": "algorythmos"}) == (400, "PATH_NOT_FOUND")
        assert await _call(app_client, {**bearer, "X-Tenant-Id": "gmail"}) == (403, "TENANT_MISMATCH")

    for email in ("one@gmail.com", "two@gmail.com"):
        with patch("app.auth.google_auth.verify_google_token", return_value=_google(email)):
            assert await _call(app_client, bearer) == (400, "PATH_NOT_FOUND")

    async with tenant_db() as session:
        tenants = {u.email: u.tenant_id for u in (await session.execute(select(UserDB))).scalars()}
    assert tenants["sam@algorythmos.com.au"] == "algorythmos"
    assert tenants["one@gmail.com"] != tenants["two@gmail.com"]
    assert tenants["one@gmail.com"].startswith("user-")


async def test_google_user_outside_allow_list_rejected(
    app_client: AsyncClient, tenant_db, strict_static, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", "algorythmos.com.au")
    with patch("app.auth.google_auth.verify_google_token", return_value=_google("outsider@gmail.com")):
        assert (await _call(app_client, {"Authorization": "Bearer google-id-token"}))[0] == 401


async def test_created_api_key_inherits_user_tenant(
    app_client: AsyncClient, tenant_db, strict_static, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", "algorythmos.com.au")
    monkeypatch.setattr(settings, "GOOGLE_TENANT_MAP", "algorythmos.com.au=algorythmos")
    with patch("app.auth.google_auth.verify_google_token", return_value=_google("dev@algorythmos.com.au")):
        response = await app_client.post(
            "/auth/keys", headers={"Authorization": "Bearer google-id-token"}, json={"name": "ci"}
        )
    assert response.status_code in (200, 201), response.text
    raw = response.json()["raw_key"]

    async with tenant_db() as session:
        key = (await session.execute(select(ApiKeyDB).where(ApiKeyDB.key_hash == hash_api_key(raw)))).scalar_one()
    assert key.tenant_id == "algorythmos"
    assert await _call(app_client, {"X-API-Key": raw}) == (400, "PATH_NOT_FOUND")
