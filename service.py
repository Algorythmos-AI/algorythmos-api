"""Compatibility shim for legacy ``service`` imports.

Non-canonical runtime logic is forbidden here.
The only deployable ASGI runtime lives in top-level app.py and is re-exported
through the ``app`` package.
"""

from __future__ import annotations

from app import app

__all__ = ["app"]
