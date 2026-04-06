"""Application configuration."""

from functools import lru_cache
from os import getenv
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseModel):
    """Typed application settings loaded from environment variables."""

    app_name: str = Field(default="After Market Agent")
    environment: str = Field(default="development")
    database_url: str = Field(default="postgresql://postgres:postgres@localhost:5432/after_market_agent")
    debug: bool = Field(default=False)
    default_watchlist_name: str = Field(default="Default Watchlist")
    email_provider: str = Field(default="mock")
    email_api_key: str | None = Field(default=None)
    email_from: str = Field(default="digest@example.com")
    digest_recipients: list[str] = Field(default_factory=lambda: ["digest@example.com"])
    digest_timezone: str = Field(default="America/Los_Angeles")
    digest_send_hour: int = Field(default=6)
    enable_scheduler: bool = Field(default=False)
    scheduled_watchlist_id: int = Field(default=1)

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables."""

        return cls(
            app_name=_get_env_or_default("APP_NAME", cls.model_fields["app_name"].default),
            environment=_get_env_or_default("ENVIRONMENT", cls.model_fields["environment"].default),
            database_url=_get_env_or_default("DATABASE_URL", cls.model_fields["database_url"].default),
            debug=getenv("DEBUG", str(cls.model_fields["debug"].default)).lower() in {"1", "true", "yes", "on"},
            default_watchlist_name=getenv(
                "DEFAULT_WATCHLIST_NAME",
                cls.model_fields["default_watchlist_name"].default,
            ),
            email_provider=_get_env_or_default("EMAIL_PROVIDER", cls.model_fields["email_provider"].default),
            email_api_key=getenv("EMAIL_API_KEY", cls.model_fields["email_api_key"].default),
            email_from=_get_env_or_default("EMAIL_FROM", cls.model_fields["email_from"].default),
            digest_recipients=_parse_recipients(
                getenv("DIGEST_RECIPIENTS", ",".join(cls.model_fields["digest_recipients"].default_factory()))
            ),
            digest_timezone=_get_env_or_default("DIGEST_TIMEZONE", cls.model_fields["digest_timezone"].default),
            digest_send_hour=int(getenv("DIGEST_SEND_HOUR", str(cls.model_fields["digest_send_hour"].default))),
            enable_scheduler=getenv(
                "ENABLE_SCHEDULER",
                str(cls.model_fields["enable_scheduler"].default),
            ).lower()
            in {"1", "true", "yes", "on"},
            scheduled_watchlist_id=int(
                getenv("SCHEDULED_WATCHLIST_ID", str(cls.model_fields["scheduled_watchlist_id"].default))
            ),
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()


def _parse_recipients(value: str) -> list[str]:
    """Parse comma-separated recipients from environment."""

    return [recipient.strip() for recipient in value.split(",") if recipient.strip()]


def _get_env_or_default(name: str, default: str) -> str:
    """Return a non-empty environment variable or a default value."""

    value = getenv(name)
    if value is None or not value.strip():
        return default
    return value
