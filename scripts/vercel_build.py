"""Vercel build step (vercel.json buildCommand): guard production, then migrate.

Runs during `vercel build`, where the Sensitive DATABASE_URL* variables are
available (they cannot be pulled to a laptop). Preview deploys share the
production database, so they never migrate; merge to main to migrate.

Production builds are refused unless ENV=prod and the settings pass the
production validator in config.py. A failed build is never promoted, so the
previous deployment keeps serving; the same problem caught at runtime would
take the live API down instead. Only variable names and validator messages are
printed, never values.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# `python scripts/vercel_build.py` puts scripts/ on sys.path, not the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRODUCTION_ENV_VALUES = {"prod", "production"}  # as app._is_production_environment()


def _production_config_errors() -> list[str]:
    """Validate production settings; return safe messages, never input values."""
    from pydantic import ValidationError

    try:
        import config

        # The import validates only once per process; load again to validate now.
        config.load_settings()
    except ValidationError as exc:
        return [
            f"{'.'.join(str(part) for part in err['loc']) or 'settings'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        ]
    except Exception as exc:  # noqa: BLE001 - report the type only; messages may carry values
        return [f"settings could not be loaded ({type(exc).__name__})"]
    return []


def main() -> int:
    env = os.getenv("VERCEL_ENV", "")
    if env != "production":
        print(f"[vercel_build] VERCEL_ENV={env or 'unset'}: skipping migrations")
        return 0
    if (os.getenv("ENV") or "").strip().lower() not in PRODUCTION_ENV_VALUES:
        print(
            "[vercel_build] refusing production build: set ENV=prod in the Vercel "
            "Production environment (see docs/runbooks/production-mode.md)"
        )
        return 1
    errors = _production_config_errors()
    if errors:
        print("[vercel_build] refusing production build: production settings are invalid")
        for message in errors:
            print(f"[vercel_build]   {message}")
        return 1
    if not (os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL")):
        print("[vercel_build] no DATABASE_URL configured: skipping migrations")
        return 0
    print("[vercel_build] production: alembic upgrade head")
    return subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
