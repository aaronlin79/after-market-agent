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

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from environment variables."""

        return cls(
            app_name=getenv("APP_NAME", cls.model_fields["app_name"].default),
            environment=getenv("ENVIRONMENT", cls.model_fields["environment"].default),
            database_url=getenv("DATABASE_URL", cls.model_fields["database_url"].default),
            debug=getenv("DEBUG", str(cls.model_fields["debug"].default)).lower() in {"1", "true", "yes", "on"},
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings.from_env()
