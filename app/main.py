"""Stage 1 FastAPI wrapper that preserves the legacy application."""

from __future__ import annotations

from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings

# The legacy FastAPI application lives in the root-level app.py module.
# Reuse its router stack so existing behaviour stays intact.
from app import build_api  # type: ignore  # noqa: E402

legacy_app = build_api()
app = legacy_app

# --- Stage 1: CORS hardening -------------------------------------------------
try:
    origins: List[str] = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
except Exception:  # pragma: no cover - defensive safeguard
    pass


# --- Stage 1: /version endpoint ----------------------------------------------
@app.get("/version", tags=["health"])
async def version():
    return {"app": "api-algorythmos", "env": settings.ENV}
