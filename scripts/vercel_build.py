"""Vercel build step (vercel.json buildCommand): migrate on production deploys only.

Runs during `vercel build`, where the Sensitive DATABASE_URL* variables are
available (they cannot be pulled to a laptop). Preview deploys share the
production database, so they never migrate; merge to main to migrate.
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    env = os.getenv("VERCEL_ENV", "")
    if env != "production":
        print(f"[vercel_build] VERCEL_ENV={env or 'unset'}: skipping migrations")
        return 0
    if not (os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL")):
        print("[vercel_build] no DATABASE_URL configured: skipping migrations")
        return 0
    print("[vercel_build] production: alembic upgrade head")
    return subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
