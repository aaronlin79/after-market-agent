"""News adapter implementations."""

from __future__ import annotations

from backend.app.core.config import Settings, get_settings
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.adapters.finnhub_adapter import FinnhubNewsAdapter
from backend.app.services.news.adapters.mock_adapter import MockNewsAdapter


def get_news_adapter(settings: Settings | None = None) -> BaseNewsAdapter:
    """Return the configured news adapter for the current environment."""

    resolved_settings = settings or get_settings()
    provider = resolved_settings.news_provider.strip().lower()

    if provider == "mock":
        return MockNewsAdapter()
    if provider == "finnhub":
        return FinnhubNewsAdapter(settings=resolved_settings)
    raise ValueError(f"Unsupported NEWS_PROVIDER: {resolved_settings.news_provider}")
