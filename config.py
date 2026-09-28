"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from typing import List

from pathlib import Path
from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_WEBHOOK_SECRET = "test_secret_change_in_production"
_LOCAL_ORIGIN_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration with ALG_* aliases
    ALG_API_KEY: str = Field(
        ...,  # Required - no fallback for production safety
        validation_alias=AliasChoices("ALG_API_KEY", "API_KEY", "api_key"),
        description="API key for authentication"
    )
    ALG_TENANT_ID: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ALG_TENANT_ID", "TENANT_ID"),
        description="Default tenant ID"
    )
    RATE_PER_MIN: int = Field(
        default=120, 
        validation_alias=AliasChoices("RATE_PER_MIN", "ALG_RATE_PER_MIN", "rate_per_min"),
        description="Rate limit per minute per tenant"
    )
    
    # New settings for Stage 1
    API_BASE: str = Field(
        default="https://api.algorythmos.com",
        description="Base API URL"
    )
    CORS_ORIGINS: str = Field(
        default="",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins"),
        description="CORS allowed origins (comma-separated). Empty means no browser origins."
    )
    ENV: str = Field(
        default="dev",
        description="Environment (dev/staging/prod)"
    )
    GOOGLE_CLIENT_ID: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_ID", "google_client_id"),
        description="Google OAuth client ID for token audience validation (optional in dev, recommended in prod)"
    )
    VENDOR_WEBHOOK_SECRET: str | None = Field(
        default=None,
        description="Secret for vendor webhook HMAC verification"
    )
    WEBHOOK_ALLOW_LEGACY_SIGNATURES: bool = Field(
        default=True,
        description="Allow legacy vendor webhook signature scheme (sha256=...)."
    )
    WEBHOOK_LEGACY_REQUIRE_TIMESTAMP: bool = Field(
        default=True,
        description="Require X-Vendor-Timestamp for legacy webhook signatures."
    )
    REDIS_URL: str | None = Field(
        default=None,
        # KV_URL / UPSTASH_REDIS_URL: names used by managed Redis integrations.
        validation_alias=AliasChoices("REDIS_URL", "redis_url", "KV_URL", "UPSTASH_REDIS_URL"),
        description="Redis URL used for distributed operational state (rate limiting, queue signalling)"
    )
    STATE_BACKEND: str = Field(
        default="auto",
        validation_alias=AliasChoices("STATE_BACKEND", "state_backend"),
        description="Operational state backend strategy: auto|redis|memory"
    )
    
    # File handling
    MAX_FILE_MB: int = Field(
        default=25,
        validation_alias=AliasChoices("MAX_FILE_MB", "max_file_mb"),
        description="Maximum file size in MB"
    )
    
    # Stage 3+ Requirements: Runs and processing limits
    RUN_MAX_FILE_BYTES: int = Field(
        default=10 * 1024 * 1024,  # 10MB default
        description="Maximum file size in bytes for run uploads"
    )
    RUN_MAX_FILES: int = Field(
        default=50,
        description="Maximum number of files per run"
    )
    
    # Webhook and security settings
    WEBHOOK_REPLAY_TTL_S: int = Field(
        default=300,  # 5 minutes
        description="Time-to-live for webhook replay protection in seconds"
    )
    WEBHOOK_REPLAY_WINDOW_S: int = Field(
        default=60,  # 1 minute
        description="Time window for webhook timestamp validation in seconds"
    )
    WEBHOOK_SECRET: str = Field(
        default=DEFAULT_WEBHOOK_SECRET,
        validation_alias=AliasChoices("WEBHOOK_SECRET", "webhook_secret"),
        description="Secret for webhook HMAC signature verification"
    )
    
    # Server-side path extraction (development only; refused in production)
    LOCAL_EXTRACT_BASE_DIR: str | None = Field(
        default=None,
        description="Directory that /extract/path and /jobs may read from. Unset disables the feature."
    )

    # Google sign-in allow-list (comma-separated). Empty: open outside production, closed in production.
    GOOGLE_ALLOWED_DOMAINS: str = Field(default="", description="Email domains allowed to sign in with Google")
    GOOGLE_ALLOWED_EMAILS: str = Field(default="", description="Individual emails allowed to sign in with Google")

    # Tenant binding (core/tenancy.py). The static key acts for ALG_TENANT_ID;
    # this deprecated list lets it act for a few more. "*" (any tenant) is for
    # local development and tests only and is refused in production.
    ALG_STATIC_KEY_ALLOWED_TENANTS: str = Field(
        default="", description="Extra tenants the static key may act for (comma-separated, deprecated)"
    )
    # Google users: "domain=tenant,..." puts a domain's users in one tenant;
    # everyone else gets a tenant of their own.
    GOOGLE_TENANT_MAP: str = Field(default="", description="Email domain to tenant mapping for Google users")

    # Data retention (document_processing/services/retention_service.py).
    RETENTION_DAYS: int = Field(default=30, description="Days before documents and derived data are removed")
    SOFT_DELETE_PURGE_DAYS: int = Field(default=7, description="Days before soft-deleted rows are removed")
    RETENTION_MODE: str = Field(default="report", description="report (count only) or enforce (delete)")
    RETENTION_ALLOW_NON_PROD: bool = Field(
        default=False, description="Allow the retention endpoint outside the Vercel production environment (tests only)"
    )
    CRON_SECRET: str | None = Field(default=None, description="Bearer secret Vercel Cron sends to scheduled endpoints")

    # Idempotency settings
    IDEMPOTENCY_TTL_S: int = Field(
        default=86400,  # 24 hours
        description="Time-to-live for idempotency key cache in seconds"
    )
    PARSE_WORKER_POLL_INTERVAL_S: float = Field(
        default=1.0,
        description="Polling interval for parser async worker in seconds"
    )
    PARSE_WORKER_MAX_ATTEMPTS: int = Field(
        default=5,
        description="Maximum parser async worker attempts before dead-lettering"
    )
    PARSE_WORKER_BASE_DELAY_S: float = Field(
        default=2.0,
        description="Base delay for parser async retry backoff in seconds"
    )
    PARSE_WORKER_MAX_DELAY_S: float = Field(
        default=120.0,
        description="Maximum parser async retry delay in seconds"
    )
    PARSE_WORKER_JITTER_S: float = Field(
        default=1.0,
        description="Maximum random jitter added to parser async retry delay"
    )
    PARSE_WORKER_LOCK_TIMEOUT_S: int = Field(
        default=300,
        description="Parser job lock timeout before stale-running reclamation"
    )
    
    # Vendor retry configuration
    VENDOR_RETRY_MAX_ATTEMPTS: int = Field(
        default=3,
        description="Maximum retry attempts for vendor API calls"
    )
    VENDOR_RETRY_BASE_DELAY_S: float = Field(
        default=0.25,
        description="Base delay in seconds for exponential backoff retries"
    )
    
    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
        description="Logging level"
    )
    
    # Optional S3 configuration (legacy)
    s3_endpoint_url: str = Field(default="", description="S3 endpoint URL")
    s3_access_key_id: str = Field(default="", description="S3 access key ID")
    s3_secret_access_key: str = Field(default="", description="S3 secret access key")
    s3_bucket: str = Field(default="", description="S3 bucket name")
    
    model_config = SettingsConfigDict(extra="ignore")
    
    @model_validator(mode='after')
    def validate_production_requirements(self) -> 'Settings':
        """Validate production environment requirements."""
        env_normalized = self.ENV.strip().lower()

        if env_normalized in {"prod", "production"} and not self.ALG_API_KEY:
            raise ValueError("ALG_API_KEY is required in production environment")
        if env_normalized in {"prod", "production"} and not self.GOOGLE_CLIENT_ID:
            raise ValueError(
                "GOOGLE_CLIENT_ID is required in production environment for secure "
                "Google token audience validation. Without it, any valid Google token "
                "would be accepted, bypassing authentication security."
            )
        if env_normalized in {"prod", "production"} and not self.REDIS_URL:
            raise ValueError(
                "REDIS_URL is required in production environment for distributed "
                "rate limiting and durable operational controls."
            )
        if env_normalized in {"prod", "production"} and self.STATE_BACKEND.strip().lower() == "memory":
            raise ValueError("STATE_BACKEND=memory is not allowed in production")
        if env_normalized in {"prod", "production"}:
            origins = self.get_cors_origins()
            if "*" in origins:
                raise ValueError("CORS_ORIGINS must list explicit origins in production, not '*'")
            local = [o for o in origins if any(f"//{h}" in o for h in _LOCAL_ORIGIN_HOSTS)]
            if local:
                raise ValueError(f"CORS_ORIGINS must not include local development origins in production: {local}")
            if self.WEBHOOK_SECRET == DEFAULT_WEBHOOK_SECRET:
                raise ValueError("WEBHOOK_SECRET must be set to a real secret in production")
            if self.LOCAL_EXTRACT_BASE_DIR:
                raise ValueError("LOCAL_EXTRACT_BASE_DIR must not be set in production")
            if not (self.ALG_TENANT_ID or "").strip():
                raise ValueError("ALG_TENANT_ID is required in production: it is the tenant the static key acts for")
            if "*" in {t.strip() for t in self.ALG_STATIC_KEY_ALLOWED_TENANTS.split(",")}:
                raise ValueError("ALG_STATIC_KEY_ALLOWED_TENANTS must not contain '*' in production")
            # Legacy vendor signatures stay off in production unless explicitly enabled.
            if "WEBHOOK_ALLOW_LEGACY_SIGNATURES" not in self.model_fields_set:
                self.WEBHOOK_ALLOW_LEGACY_SIGNATURES = False
        if self.RETENTION_MODE.strip().lower() not in {"report", "enforce"}:
            raise ValueError("RETENTION_MODE must be 'report' or 'enforce'")
        if self.RETENTION_DAYS < 1 or self.SOFT_DELETE_PURGE_DAYS < 1:
            raise ValueError("RETENTION_DAYS and SOFT_DELETE_PURGE_DAYS must be at least 1")
        if env_normalized in {"prod", "production"} and not (self.CRON_SECRET or "").strip():
            raise ValueError("CRON_SECRET is required in production: it authenticates scheduled jobs")
        if self.PARSE_WORKER_MAX_ATTEMPTS < 1:
            raise ValueError("PARSE_WORKER_MAX_ATTEMPTS must be >= 1")
        if self.PARSE_WORKER_POLL_INTERVAL_S <= 0:
            raise ValueError("PARSE_WORKER_POLL_INTERVAL_S must be > 0")
        if self.PARSE_WORKER_BASE_DELAY_S <= 0 or self.PARSE_WORKER_MAX_DELAY_S <= 0:
            raise ValueError("PARSE_WORKER retry delays must be > 0")
        if self.PARSE_WORKER_LOCK_TIMEOUT_S <= 0:
            raise ValueError("PARSE_WORKER_LOCK_TIMEOUT_S must be > 0")
        return self
    
    def google_allowed_domains(self) -> set[str]:
        return {d.strip().lower().lstrip("@") for d in self.GOOGLE_ALLOWED_DOMAINS.split(",") if d.strip()}

    def google_allowed_emails(self) -> set[str]:
        return {e.strip().lower() for e in self.GOOGLE_ALLOWED_EMAILS.split(",") if e.strip()}

    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from the configuration."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
    
    @property
    def api_key(self) -> str:
        """Legacy property for backward compatibility."""
        return self.ALG_API_KEY
    
    @property
    def rate_per_min(self) -> int:
        """Legacy property for backward compatibility."""
        return self.RATE_PER_MIN
    
    @property
    def max_file_mb(self) -> int:
        """Legacy property for backward compatibility."""
        return self.MAX_FILE_MB
    
    @property
    def max_file_bytes(self) -> int:
        """Get maximum file size in bytes."""
        return self.MAX_FILE_MB * 1024 * 1024


def _default_env_file() -> tuple[str | None, str | None]:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        return str(env_path), "utf-8"
    project_env = Path.cwd() / ".env"
    if project_env.exists():
        return str(project_env), "utf-8"
    return None, None


def load_settings() -> Settings:
    env_file, encoding = _default_env_file()
    kwargs: dict[str, object] = {}
    if env_file:
        kwargs["_env_file"] = env_file
    if encoding:
        kwargs["_env_file_encoding"] = encoding
    return Settings(**kwargs)


# Global settings instance
settings = load_settings()
