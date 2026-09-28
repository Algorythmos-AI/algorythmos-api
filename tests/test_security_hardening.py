"""Regression tests for the security hardening of authentication and unsafe endpoints.

Each test pins one fix: constant-time key checks with Bearer fall-through,
no idempotency replay or quota use before authentication, single rate-limit
counting, confined server-side paths, webhook SSRF protection, authenticated
metrics, documented security schemes, strict CORS, and the Google allow-list.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from config import settings
from core.security import UnsafeOutboundURL, assert_public_https_url, bearer_token, secure_equals
from fixtures.synthetic_invoices import write_synthetic_invoices

app_main = sys.modules["app_main"]


def _headers(tenant: str = "tenant-sec", **extra: str) -> dict[str, str]:
    return {"X-API-Key": settings.ALG_API_KEY, "X-Tenant-Id": tenant, **extra}


def _allowed_dir(name: str) -> Path:
    base = Path(os.environ["LOCAL_EXTRACT_BASE_DIR"])
    path = base / f"alg-sec-{name}-{os.getpid()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- credential helpers --------------------------------------------------------


def test_secure_equals_and_bearer_parsing() -> None:
    assert secure_equals("abc", "abc")
    assert not secure_equals("abc", "abd")
    assert bearer_token("Bearer tok") == "tok"
    assert bearer_token("bearer tok") == "tok"
    assert bearer_token("Bearer ") is None
    assert bearer_token("Basic tok") is None
    assert bearer_token(None) is None


async def test_bearer_mismatch_falls_through_to_valid_api_key(app_client: AsyncClient) -> None:
    missing = _allowed_dir("fallthrough") / "missing"
    response = await app_client.post(
        "/extract/path",
        headers=_headers(Authorization="Bearer not-the-key"),
        json={"input_path": str(missing)},
    )
    # Authenticated by X-API-Key: the request reaches the path check, not a 401.
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PATH_NOT_FOUND"


async def test_wrong_key_rejected(app_client: AsyncClient) -> None:
    response = await app_client.post(
        "/extract/path",
        headers={"X-API-Key": "wrong", "X-Tenant-Id": "tenant-sec"},
        json={"input_path": "/x"},
    )
    assert response.status_code == 401


# --- idempotency is never served before authentication --------------------------


async def test_idempotent_replay_requires_authentication(app_client: AsyncClient) -> None:
    folder = _allowed_dir("idem")
    write_synthetic_invoices(folder)
    body = {"input_path": str(folder)}
    key = f"sec-idem-{os.getpid()}"

    first = await app_client.post("/extract/path", headers=_headers(**{"Idempotency-Key": key}), json=body)
    assert first.status_code == 200, first.text

    replay = await app_client.post(
        "/extract/path",
        headers={"X-Tenant-Id": "tenant-sec", "Idempotency-Key": key},
        json=body,
    )
    assert replay.status_code == 401
    assert "x-idempotency-replay" not in replay.headers

    authed_replay = await app_client.post("/extract/path", headers=_headers(**{"Idempotency-Key": key}), json=body)
    assert authed_replay.status_code == 200
    assert authed_replay.headers.get("x-idempotency-replay") == "true"


# --- rate limiting counts authenticated requests exactly once --------------------


@pytest.fixture
async def low_limit_client(monkeypatch):
    monkeypatch.setattr(settings, "RATE_PER_MIN", 3)
    fresh_app = app_main.build_api()
    async with AsyncClient(transport=ASGITransport(app=fresh_app), base_url="http://testserver") as client:
        yield client


async def test_unauthenticated_requests_do_not_consume_tenant_quota(low_limit_client: AsyncClient) -> None:
    for _ in range(6):
        response = await low_limit_client.get("/schemas", headers={"X-Tenant-Id": "tenant-quota"})
        assert response.status_code == 401
    response = await low_limit_client.get("/schemas", headers=_headers("tenant-quota"))
    assert response.status_code != 429


async def test_each_authenticated_request_counted_once(low_limit_client: AsyncClient) -> None:
    statuses = [
        (await low_limit_client.get("/schemas", headers=_headers("tenant-once"))).status_code for _ in range(4)
    ]
    # Limit of 3 per minute: three requests pass, the fourth is limited.
    # (Double counting would have limited the second request.)
    assert 429 not in statuses[:3], statuses
    assert statuses[3] == 429, statuses


# --- server-side paths are confined ---------------------------------------------


async def test_path_outside_base_dir_is_forbidden(app_client: AsyncClient) -> None:
    for path in ("/etc", "/", str(Path(os.environ["LOCAL_EXTRACT_BASE_DIR"]) / ".." / "..")):
        response = await app_client.post("/extract/path", headers=_headers(), json={"input_path": path})
        assert response.status_code == 403, path
        assert response.json()["detail"]["code"] == "PATH_NOT_ALLOWED"


async def test_paths_disabled_without_base_dir(app_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "LOCAL_EXTRACT_BASE_DIR", None)
    response = await app_client.post("/extract/path", headers=_headers(), json={"input_path": "/tmp"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LOCAL_PATHS_DISABLED"


async def test_paths_disabled_in_production(app_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENV", "prod")
    folder = _allowed_dir("prod")
    response = await app_client.post("/extract/path", headers=_headers(), json={"input_path": str(folder)})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LOCAL_PATHS_DISABLED"


async def test_job_input_path_is_confined(app_client: AsyncClient) -> None:
    response = await app_client.post("/jobs", headers=_headers(), json={"input_path": "/etc"})
    assert response.status_code == 403


# --- webhook SSRF ------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.5/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/hook",
    ],
)
def test_unsafe_webhook_urls_rejected(url: str) -> None:
    with pytest.raises(UnsafeOutboundURL):
        assert_public_https_url(url)


def test_public_https_webhook_url_accepted() -> None:
    assert_public_https_url("https://93.184.216.34/hook")


async def test_job_with_private_webhook_rejected(app_client: AsyncClient) -> None:
    folder = _allowed_dir("webhook")
    response = await app_client.post(
        "/jobs",
        headers=_headers(),
        json={"input_path": str(folder), "webhook_url": "https://127.0.0.1/hook"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "WEBHOOK_URL_REJECTED"


# --- metrics, OpenAPI, CORS ----------------------------------------------------------


async def test_metrics_requires_api_key(app_client: AsyncClient) -> None:
    assert (await app_client.get("/metrics")).status_code == 401
    ok = await app_client.get("/metrics", headers={"X-API-Key": settings.ALG_API_KEY})
    assert ok.status_code == 200


async def test_openapi_declares_security_schemes(app_client: AsyncClient) -> None:
    schema = (await app_client.get("/openapi.json")).json()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert schemes["BearerAuth"]["scheme"].lower() == "bearer"
    extract = schema["paths"]["/extract/path"]["post"]
    assert {"ApiKeyAuth": []} in extract["security"]


async def test_cors_does_not_echo_unknown_origins(app_client: AsyncClient) -> None:
    response = await app_client.options(
        "/schemas",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"
    assert response.headers.get("access-control-allow-credentials") != "true"


# --- Google sign-in allow-list ---------------------------------------------------------


def test_google_allow_list(monkeypatch) -> None:
    allowed = app_main._google_account_allowed
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", "")
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", "")
    monkeypatch.setattr(settings, "ENV", "dev")
    assert allowed("anyone@gmail.com")
    monkeypatch.setattr(settings, "ENV", "prod")
    assert not allowed("anyone@gmail.com")

    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", "algorythmos.com.au")
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_EMAILS", "partner@example.org")
    assert allowed("someone@algorythmos.com.au")
    assert allowed("Partner@Example.org")
    assert not allowed("someone@gmail.com")
    assert not allowed("not-an-email")


async def test_google_signin_denied_for_unlisted_account(app_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "GOOGLE_ALLOWED_DOMAINS", "algorythmos.com.au")
    user = SimpleNamespace(email="outsider@gmail.com", name="Outsider", picture=None, sub="123")
    with patch("app.auth.google_auth.verify_google_token", return_value=user):
        response = await app_client.post("/auth/google", headers={"Authorization": "Bearer token"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACCOUNT_NOT_ALLOWED"
