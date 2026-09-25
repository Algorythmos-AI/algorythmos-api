"""normalize_database_url turns provider URLs into asyncpg-compatible ones."""

from database import normalize_database_url


def test_neon_url_gets_asyncpg_scheme_and_ssl():
    raw = "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    assert normalize_database_url(raw) == "postgresql+asyncpg://u:p@ep-x.aws.neon.tech/neondb?ssl=require"


def test_legacy_postgres_scheme_is_rewritten():
    assert normalize_database_url("postgres://u:p@h/db").startswith("postgresql+asyncpg://")


def test_sslmode_disable_drops_ssl():
    assert normalize_database_url("postgresql://u:p@h/db?sslmode=disable") == "postgresql+asyncpg://u:p@h/db"


def test_other_urls_pass_through():
    for url in ("sqlite+aiosqlite:///./dev.db", "postgresql+asyncpg://u:p@h/db?ssl=require"):
        assert normalize_database_url(url) == url
