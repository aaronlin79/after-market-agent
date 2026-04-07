"""Email provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseEmailProvider(ABC):
    """Abstract email delivery provider."""

    @abstractmethod
    def send_email(self, to: list[str], subject: str, html: str, text: str) -> dict[str, Any]:
        """Send an email message."""
