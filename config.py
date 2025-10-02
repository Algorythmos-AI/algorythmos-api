"""Configuration management using Pydantic Settings."""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration
    api_key: str = Field(..., description="API key for authentication")
    cors_origins: str = Field(default="https://app.algorythmos.fr", description="CORS allowed origins (comma-separated)")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Rate limiting and file size
    rate_per_min: int = Field(default=120, description="Rate limit per minute per tenant")
    max_file_mb: int = Field(default=25, description="Maximum file size in MB")
    
    # Optional S3 configuration
    s3_endpoint_url: str = Field(default="", description="S3 endpoint URL")
    s3_access_key_id: str = Field(default="", description="S3 access key ID")
    s3_secret_access_key: str = Field(default="", description="S3 secret access key")
    s3_bucket: str = Field(default="", description="S3 bucket name")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from the configuration."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
    
    @property
    def max_file_bytes(self) -> int:
        """Get maximum file size in bytes."""
        return self.max_file_mb * 1024 * 1024


# Global settings instance
settings = Settings()