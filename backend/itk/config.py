"""Application settings, loaded from environment variables (and `.env` files in development)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
        populate_by_name=True,
    )

    app_name: str = "ITK API"
    environment: Literal["development", "test", "staging", "production"] = "development"

    # Public URLs. `app_url` is the Next.js site (links in emails, OAuth landing pages);
    # `backend_api_url` is where Google/Spotify send OAuth callbacks.
    app_url: str = Field(default="http://localhost:3000", alias="NEXT_PUBLIC_APP_URL")
    backend_api_url: str = Field(default="http://localhost:8000", alias="BACKEND_API_URL")

    database_url: str = Field(default="sqlite:///./itk-dev.db", alias="DATABASE_URL")
    database_url_unpooled: str | None = Field(default=None, alias="DATABASE_URL_UNPOOLED")

    # LLM access via OpenRouter. Without a key, every AI step falls back to heuristics.
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    openrouter_model: str = Field(default="openai/gpt-5.2", alias="OPENROUTER_MODEL")
    openrouter_search_model: str = Field(default="perplexity/sonar", alias="OPENROUTER_SEARCH_MODEL")
    openrouter_writing_model: str = Field(default="openai/gpt-5.2", alias="OPENROUTER_WRITING_MODEL")

    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    spotify_client_id: str | None = Field(default=None, alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str | None = Field(default=None, alias="SPOTIFY_CLIENT_SECRET")

    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    resend_from_email: str = Field(default="ITK <onboarding@resend.dev>", alias="RESEND_FROM_EMAIL")
    resend_reply_to_email: str | None = Field(default=None, alias="RESEND_REPLY_TO_EMAIL")
    resend_inbound_webhook_secret: str | None = Field(default=None, alias="RESEND_INBOUND_WEBHOOK_SECRET")
    # When no Resend key is configured, outgoing mail is written here as .html files.
    email_outbox_dir: Path = Field(default=Path(".outbox"), alias="EMAIL_OUTBOX_DIR")

    session_secret: str = Field(default=INSECURE_DEFAULT_SECRET, alias="SESSION_SECRET")
    token_encryption_key: str | None = Field(default=None, alias="TOKEN_ENCRYPTION_KEY")
    api_cron_secret: str = Field(default=INSECURE_DEFAULT_SECRET, alias="API_CRON_SECRET")

    rate_limit_signup: str = Field(default="10/minute", alias="RATE_LIMIT_SIGNUP")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS"
    )
    pilot_cities: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["austin", "san antonio"], alias="PILOT_CITIES"
    )

    @field_validator("cors_origins", "pilot_cities", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("pilot_cities")
    @classmethod
    def _lowercase_cities(cls, value: list[str]) -> list[str]:
        return [city.lower() for city in value]

    @model_validator(mode="after")
    def _require_real_secrets_in_production(self) -> "Settings":
        if self.environment == "production":
            weak = [
                name
                for name, value in (("SESSION_SECRET", self.session_secret), ("API_CRON_SECRET", self.api_cron_secret))
                if value == INSECURE_DEFAULT_SECRET
            ]
            if weak:
                raise ValueError(f"Set {', '.join(weak)} before running in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def normalize_database_url(url: str) -> str:
    """Point bare Postgres URLs (as Neon/Heroku hand them out) at the psycopg 3 driver."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
