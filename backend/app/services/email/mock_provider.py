"""Mock email provider for local development and tests."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from backend.app.services.email.base import BaseEmailProvider

logger = logging.getLogger(__name__)


class MockEmailProvider(BaseEmailProvider):
    """Log email payloads and return deterministic success responses."""

    def send_email(self, to: list[str], subject: str, html: str, text: str) -> dict[str, Any]:
        logger.info(
            "Mock email send provider=%s recipients=%s subject=%s",
            "mock",
            to,
            subject,
        )
        message_id = hashlib.sha256(f"{subject}|{'|'.join(sorted(to))}".encode("utf-8")).hexdigest()[:16]
        return {
            "provider": "mock",
            "recipient_count": len(to),
            "message_id": message_id,
            "status": "sent",
        }
