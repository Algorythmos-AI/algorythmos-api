"""Vercel serverless entrypoint for the FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is importable when running on Vercel
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

from app import app as root_app

# Expose the main application for Vercel serverless
# The root_app already has all routes, middleware, and OpenAPI configured
app = root_app

__all__ = ["app"]
