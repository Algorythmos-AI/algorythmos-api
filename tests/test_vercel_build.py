"""The Vercel build step refuses production builds that would run misconfigured."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SECRET_VALUES = ("guard-api-key-4f1c", "guard-webhook-secret-9a2e", "guard-cron-secret-7d3b")


def _load_build_script():
    spec = importlib.util.spec_from_file_location("vercel_build", ROOT / "scripts" / "vercel_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def build(monkeypatch):
    """The build script with migrations replaced by a recording fake."""
    module = _load_build_script()
    calls: list[list[str]] = []

    class _Completed:
        returncode = 0

    def fake_run(args, check=False):
        calls.append(list(args))
        return _Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    for name in ("VERCEL_ENV", "ENV", "DATABASE_URL", "DATABASE_URL_UNPOOLED"):
        monkeypatch.delenv(name, raising=False)
    module.calls = calls
    module.completed = _Completed
    return module


@pytest.fixture
def production_settings(monkeypatch):
    """Environment that passes the production validator in config.py."""
    values = {
        "ALG_API_KEY": SECRET_VALUES[0],
        "GOOGLE_CLIENT_ID": "guard.apps.googleusercontent.com",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "STATE_BACKEND": "redis",
        "CORS_ORIGINS": "https://app.example.com",
        "WEBHOOK_SECRET": SECRET_VALUES[1],
        "CRON_SECRET": SECRET_VALUES[2],
        "ALG_TENANT_ID": "service",
        "ALG_STATIC_KEY_ALLOWED_TENANTS": "service",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    # conftest.py sets these for the legacy suite; production refuses them.
    monkeypatch.delenv("LOCAL_EXTRACT_BASE_DIR", raising=False)


@pytest.mark.parametrize("env_value", ["dev", None, ""])
def test_production_build_refused_unless_env_is_prod(build, monkeypatch, capsys, env_value):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://guard.invalid/db")
    if env_value is not None:
        monkeypatch.setenv("ENV", env_value)

    assert build.main() == 1
    assert build.calls == []
    assert "set ENV=prod" in capsys.readouterr().out


@pytest.mark.parametrize("env_value", [" PROD ", "production"])
def test_production_build_accepted_when_prod_config_validates(build, production_settings, monkeypatch, env_value):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENV", env_value)

    assert build.main() == 0
    assert build.calls == []  # no DATABASE_URL: nothing to migrate


def test_invalid_production_settings_refused_without_printing_values(
    build, production_settings, monkeypatch, capsys
):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("DATABASE_URL", "postgresql://guard.invalid/db")

    assert build.main() == 1
    assert build.calls == []
    out = capsys.readouterr().out
    assert "CORS_ORIGINS must list explicit origins" in out
    for secret in SECRET_VALUES:
        assert secret not in out


def test_production_build_migrates_and_passes_through_the_exit_code(build, production_settings, monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql://guard.invalid/db")
    monkeypatch.setattr(build.completed, "returncode", 3)

    assert build.main() == 3
    assert build.calls == [[sys.executable, "-m", "alembic", "upgrade", "head"]]


def test_unpooled_database_url_alone_triggers_migration(build, production_settings, monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgresql://guard.invalid/db")

    assert build.main() == 0
    assert build.calls == [[sys.executable, "-m", "alembic", "upgrade", "head"]]


@pytest.mark.parametrize("vercel_env", ["preview", "development", None])
def test_non_production_builds_skip_the_guard_and_migrations(build, monkeypatch, vercel_env):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "postgresql://guard.invalid/db")
    if vercel_env is not None:
        monkeypatch.setenv("VERCEL_ENV", vercel_env)

    assert build.main() == 0
    assert build.calls == []


def test_settings_validation_errors_do_not_echo_input(production_settings, monkeypatch):
    from config import Settings

    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    rendered = str(excinfo.value)
    for secret in SECRET_VALUES:
        assert secret not in rendered
