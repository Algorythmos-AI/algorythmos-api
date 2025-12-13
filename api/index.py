"""Vercel serverless entrypoint for the FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

# Ensure repository root is importable when running on Vercel
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from app import app as root_app

app = FastAPI()


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Expose existing application routes
app.mount("/", root_app)

__all__ = ["app"]
