from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ITK API"
    environment: Literal["development", "staging", "production"] = "development"
    app_url: str = Field(default="http://localhost:3000", alias="NEXT_PUBLIC_APP_URL")
    backend_api_url: str = "http://localhost:8000"

    database_url: str = Field(alias="DATABASE_URL")
    database_url_unpooled: str | None = Field(default=None, alias="DATABASE_URL_UNPOOLED")

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")

    spotify_client_id: str | None = Field(default=None, alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str | None = Field(default=None, alias="SPOTIFY_CLIENT_SECRET")

    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    resend_from_email: str = "ITK <hello@itk.so>"

    session_secret: str = "change-me"
    token_encryption_key: str | None = None
    api_cron_secret: str = "change-me"

    rate_limit_signup: str = "10/minute"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return ["http://localhost:3000"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
