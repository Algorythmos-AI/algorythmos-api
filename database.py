"""Shared database configuration and base classes.

This module is intentionally at the root level (not in app/) to avoid
circular import issues in serverless environments like Vercel.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models."""
    pass


# libpq-only query parameters that asyncpg rejects as unknown connect() kwargs.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding"}


def normalize_database_url(raw: str) -> str:
    """Make a provider connection string usable by SQLAlchemy's asyncpg driver.

    Neon (via the Vercel integration) hands out
    ``postgresql://user:pass@host/db?sslmode=require&channel_binding=require``.
    For that scheme SQLAlchemy picks psycopg2, which is not installed, and asyncpg
    refuses the libpq-only parameters. Rewrite the scheme to ``postgresql+asyncpg``
    and translate ``sslmode`` into asyncpg's ``ssl``. Any other URL (SQLite, an
    already-qualified driver) passes through unchanged.
    """
    if not raw.startswith(("postgres://", "postgresql://")):
        return raw
    parts = urlsplit(raw)
    params = parse_qsl(parts.query, keep_blank_values=True)
    sslmode = next((v for k, v in params if k == "sslmode"), None)
    query = [(k, v) for k, v in params if k not in _LIBPQ_ONLY_PARAMS]
    if sslmode and sslmode != "disable" and not any(k == "ssl" for k, _ in query):
        query.append(("ssl", "require"))
    return urlunsplit(parts._replace(scheme="postgresql+asyncpg", query=urlencode(query)))


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./dev.db"))

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async generator for database sessions.
    
    Uses AsyncGenerator type to avoid Pydantic schema generation issues
    with SQLAlchemy's internal types like _AsyncSessionBind.
    """
    async with async_session_factory() as session:
        yield session

