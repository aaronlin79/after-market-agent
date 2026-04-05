"""Mock news adapter for local development and tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.app.services.news.adapters.base import BaseNewsAdapter


class MockNewsAdapter(BaseNewsAdapter):
    """Return deterministic mock financial news items."""

    def fetch_news(
        self,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Return mocked news items for the requested symbols."""

        items: list[dict[str, Any]] = []
        window_end = end_time.astimezone(UTC)

        for index, symbol in enumerate(sorted(set(symbols))):
            published_primary = window_end - timedelta(hours=index + 1)
            published_secondary = window_end - timedelta(hours=index + 2)

            items.append(
                {
                    "external_id": f"{symbol}-earnings-preview",
                    "title": f"{symbol} draws investor focus ahead of earnings",
                    "body_text": f"{symbol} is attracting analyst attention before the next earnings call.",
                    "url": f"https://mocknews.local/{symbol.lower()}/earnings-preview",
                    "source_name": "MockWire",
                    "published_at": published_primary,
                    "metadata_json": {"symbols": [symbol], "provider": "mock", "topic": "earnings"},
                }
            )
            items.append(
                {
                    "external_id": f"{symbol}-sector-move",
                    "title": f"{symbol} tracks broader semiconductor move",
                    "body_text": "",
                    "url": f"https://mocknews.local/{symbol.lower()}/sector-move",
                    "source_name": "MockWire",
                    "published_at": published_secondary,
                    "metadata_json": {"symbols": [symbol], "provider": "mock", "topic": "sector"},
                }
            )

        if symbols:
            shared_symbols = sorted(set(symbols))[:2]
            items.append(
                {
                    "external_id": "market-open-shared-1",
                    "title": "Chip stocks rise after upbeat overnight demand signals",
                    "body_text": "Several semiconductor names moved higher after suppliers signaled stable demand.",
                    "url": "https://mocknews.local/shared/chip-stocks-rise",
                    "source_name": "MockWire",
                    "published_at": window_end - timedelta(minutes=45),
                    "metadata_json": {"symbols": shared_symbols, "provider": "mock", "topic": "market-open"},
                }
            )
            items.append(
                {
                    "external_id": "market-open-shared-duplicate",
                    "title": "Chip stocks rise after upbeat overnight demand signals",
                    "body_text": "Semiconductor shares were active in premarket trading after overnight supplier commentary.",
                    "url": "https://mocknews.local/shared/chip-stocks-rise",
                    "source_name": "StreetDesk",
                    "published_at": window_end - timedelta(minutes=30),
                    "metadata_json": {"symbols": shared_symbols, "provider": "mock", "topic": "market-open"},
                }
            )

        return [
            item
            for item in items
            if start_time <= item["published_at"] <= end_time
        ]
