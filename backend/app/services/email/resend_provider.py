"""Minimal Resend provider scaffold."""

from __future__ import annotations

import json
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from backend.app.services.email.base import BaseEmailProvider


class ResendEmailProvider(BaseEmailProvider):
    """Send email with Resend."""

    def __init__(self, api_key: str, from_address: str) -> None:
        if not api_key:
            raise ValueError("EMAIL_API_KEY is required when EMAIL_PROVIDER is set to resend.")
        if not from_address:
            raise ValueError("EMAIL_FROM is required when EMAIL_PROVIDER is set to resend.")
        self.api_key = api_key
        self.from_address = from_address

    def send_email(self, to: list[str], subject: str, html: str, text: str) -> dict[str, Any]:
        payload = json.dumps(
            {
                "from": self.from_address,
                "to": to,
                "subject": subject,
                "html": html,
                "text": text,
            }
        ).encode("utf-8")
        http_request = request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Resend email send failed with status {exc.code}.") from exc
        except URLError as exc:
            raise RuntimeError("Resend email send failed due to a network error.") from exc

        return {
            "provider": "resend",
            "recipient_count": len(to),
            "message_id": data.get("id"),
            "status": "sent",
        }
