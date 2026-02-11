"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from typing import List

from pathlib import Path
from pydantic import Field, AliasChoices, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="https://api.algorythmos.fr",
        description="Base API URL"
    )
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,https://ui-algorythmos.vercel.app,https://app.algorythmos.com,https://app.algorythmos.fr",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins"),
        description="CORS allowed origins (comma-separated)"
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
        default="test_secret_change_in_production",
        validation_alias=AliasChoices("WEBHOOK_SECRET", "webhook_secret"),
        description="Secret for webhook HMAC signature verification"
    )
    
    # Idempotency settings
    IDEMPOTENCY_TTL_S: int = Field(
        default=86400,  # 24 hours
        description="Time-to-live for idempotency key cache in seconds"
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
        if self.ENV == "prod" and not self.ALG_API_KEY:
            raise ValueError("ALG_API_KEY is required in production environment")
        if self.ENV == "prod" and not self.GOOGLE_CLIENT_ID:
            raise ValueError(
                "GOOGLE_CLIENT_ID is required in production environment for secure "
                "Google token audience validation. Without it, any valid Google token "
                "would be accepted, bypassing authentication security."
            )
        return self
    
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
