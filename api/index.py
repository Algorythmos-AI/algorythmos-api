"""Vercel serverless entrypoint for the FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is importable when running on Vercel
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

# Canonical runtime: top-level app.py (re-exported by the app package).
from app import app as canonical_app

# Expose the canonical FastAPI application for Vercel.
app = canonical_app

__all__ = ["app"]
