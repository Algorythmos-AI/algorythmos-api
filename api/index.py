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

app = FastAPI(
    title="Algorythmos API",
    description="Your FastAPI app",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Expose existing application routes
app.mount("/", root_app)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Algorythmos API",
        version="0.1.0",
        description="Your API",
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

__all__ = ["app"]
