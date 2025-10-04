"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from typing import List

from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration with ALG_* aliases
    ALG_API_KEY: str = Field(
        default="algo_dWukMWn8YyFfkdnL4yITRgp8042vYbz1ckk2aY3dv",  # Fallback for deployment
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
        default="http://localhost:3000,https://app.algorythmos.fr",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins"),
        description="CORS allowed origins (comma-separated)"
    )
    ENV: str = Field(
        default="dev",
        description="Environment (dev/staging/prod)"
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
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
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


# Global settings instance
settings = Settings()