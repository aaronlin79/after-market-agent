"""Base interface for news providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class BaseNewsAdapter(ABC):
    """Abstract interface for fetching normalized news items."""

    @abstractmethod
    def fetch_news(
        self,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch news items for symbols within a time window."""
