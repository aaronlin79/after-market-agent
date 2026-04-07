"""Brevo transactional email provider."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from backend.app.services.email.base import BaseEmailProvider

logger = logging.getLogger(__name__)

BREVO_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailProvider(BaseEmailProvider):
    """Send digest emails through Brevo."""

    def __init__(self, api_key: str, from_address: str, from_name: str | None = None) -> None:
        if not api_key:
            raise ValueError("BREVO_API_KEY is required when EMAIL_PROVIDER is set to brevo.")
        if not from_address:
            raise ValueError("EMAIL_FROM is required when EMAIL_PROVIDER is set to brevo.")
        self.api_key = api_key
        self.from_address = from_address
        self.from_name = from_name or "After Market Agent"

    def send_email(self, to: list[str], subject: str, html: str, text: str) -> dict[str, Any]:
        logger.info("Brevo email send start provider=brevo recipients=%s subject=%s", to, subject)
        payload = json.dumps(
            {
                "sender": {
                    "name": self.from_name,
                    "email": self.from_address,
                },
                "to": [{"email": recipient} for recipient in to],
                "subject": subject,
                "htmlContent": html,
                "textContent": text,
            }
        ).encode("utf-8")
        http_request = request.Request(
            BREVO_EMAIL_URL,
            data=payload,
            headers={
                "accept": "application/json",
                "api-key": self.api_key,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _read_error_body(exc)
            raise RuntimeError(f"Brevo email send failed with status {exc.code}. {detail}".strip()) from exc
        except URLError as exc:
            raise RuntimeError("Brevo email send failed due to a network error.") from exc

        logger.info("Brevo email send success provider=brevo recipients=%s subject=%s", to, subject)
        return {
            "provider": "brevo",
            "recipient_count": len(to),
            "message_id": data.get("messageId"),
            "status": "sent",
        }


def _read_error_body(error: HTTPError) -> str:
    try:
        payload = error.read().decode("utf-8").strip()
    except Exception:
        return ""
    return payload
