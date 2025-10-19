"""Re-export database utilities from root-level database module.

This module exists for backward compatibility and to avoid breaking
existing imports from app.database.
"""

from __future__ import annotations

# Import and re-export from root-level database module
from database import Base, DATABASE_URL, engine, async_session_factory, get_session

__all__ = ["Base", "DATABASE_URL", "engine", "async_session_factory", "get_session"]
