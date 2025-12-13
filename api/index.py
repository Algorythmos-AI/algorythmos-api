"""Vercel serverless entrypoint for the FastAPI application."""

import sys
from pathlib import Path

# Ensure repository root is importable when running on Vercel
ROOT = Path(__file__).resolve().parents[1]
ROOT_STR = str(ROOT)
if ROOT_STR not in sys.path:
    sys.path.insert(0, ROOT_STR)

# The ``app`` package lazily loads the FastAPI instance from app.py
from app import app

__all__ = ["app"]