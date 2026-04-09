"""Finnhub-backed news adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.core.config import Settings, get_settings
from backend.app.services.news.adapters.base import BaseNewsAdapter

FINNHUB_COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"


class FinnhubNewsAdapter(BaseNewsAdapter):
    """Fetch company news from Finnhub."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        fetch_json: Callable[[str], Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.news_api_key:
            raise ValueError("NEWS_API_KEY is required when NEWS_PROVIDER=finnhub.")
        self.fetch_json = fetch_json or self._fetch_json

    def fetch_news(
        self,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch Finnhub company news for the given symbols and window."""

        items: list[dict[str, Any]] = []
        for symbol in sorted(set(symbols)):
            query = urlencode(
                {
                    "symbol": symbol,
                    "from": start_time.date().isoformat(),
                    "to": end_time.date().isoformat(),
                    "token": self.settings.news_api_key,
                }
            )
            payload = self.fetch_json(f"{FINNHUB_COMPANY_NEWS_URL}?{query}")
            if not isinstance(payload, list):
                raise ValueError("Finnhub returned an unexpected payload shape.")

            for raw_item in payload:
                published_at = datetime.fromtimestamp(int(raw_item["datetime"]), tz=UTC)
                if published_at < start_time.astimezone(UTC) or published_at > end_time.astimezone(UTC):
                    continue

                title = str(raw_item.get("headline") or "").strip()
                url = str(raw_item.get("url") or "").strip()
                if not title or not url:
                    continue

                body_text = (
                    str(raw_item.get("summary") or "").strip()
                    or str(raw_item.get("description") or "").strip()
                    or title
                )
                provider_id = raw_item.get("id")
                items.append(
                    {
                        "external_id": str(provider_id).strip() if provider_id is not None else None,
                        "title": title,
                        "body_text": body_text,
                        "url": url,
                        "source_name": str(raw_item.get("source") or "Finnhub").strip(),
                        "published_at": published_at,
                        "metadata_json": {
                            "provider": "finnhub",
                            "symbol": symbol,
                            "symbols": [symbol],
                            "category": raw_item.get("category"),
                            "image": raw_item.get("image"),
                            "related": raw_item.get("related"),
                            "provider_id": provider_id,
                        },
                    }
                )

        return items

    def _fetch_json(self, url: str) -> Any:
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.settings.openai_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
