"""Vercel serverless entrypoint for the FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# Ensure repository root is importable when running on Vercel
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from app import app as root_app

# Reuse the main application but align metadata and documentation endpoints for Vercel
app: FastAPI = root_app
app.root_path = ""
app.docs_url = "/docs"
app.redoc_url = "/redoc"
app.title = "Algorythmos API"
app.description = "Your FastAPI app"
app.version = "0.1.0"


@app.get("/", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

__all__ = ["app"]
