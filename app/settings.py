"""Application settings sourced from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ALG_API_KEY: str = Field(validation_alias=AliasChoices("ALG_API_KEY", "API_KEY"))
    ALG_TENANT_ID: str | None = None
    RATE_PER_MIN: int = Field(120, validation_alias=AliasChoices("RATE_PER_MIN", "ALG_RATE_PER_MIN"))

    API_BASE: str = "https://api.algorythmos.fr"
    CORS_ORIGINS: str = "http://localhost:3000,https://app.algorythmos.fr"
    ENV: str = "dev"
    VENDOR_WEBHOOK_SECRET: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
