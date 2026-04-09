"""Minimal Resend provider scaffold."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError

from backend.app.services.email.base import BaseEmailProvider

logger = logging.getLogger(__name__)


class ResendEmailProvider(BaseEmailProvider):
    """Send email with Resend."""

    def __init__(self, api_key: str, from_address: str, from_name: str | None = None) -> None:
        if not api_key:
            raise ValueError("RESEND_API_KEY is required when EMAIL_PROVIDER is set to resend.")
        if not from_address:
            raise ValueError("EMAIL_FROM is required when EMAIL_PROVIDER is set to resend.")
        self.api_key = api_key
        self.from_address = from_address
        self.from_name = from_name or "After Market Agent"

    def send_email(self, to: list[str], subject: str, html: str, text: str) -> dict[str, Any]:
        logger.info(
            "Resend email send start provider=resend sender=%s recipients=%s subject=%s",
            self.from_address,
            to,
            subject,
        )
        payload = json.dumps(
            {
                "from": f"{self.from_name} <{self.from_address}>",
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
                "User-Agent": "after-hours-agent/1.0",
            },
            method="POST",
        )
        try:
            with request.urlopen(http_request) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = _read_error_body(exc)
            logger.error(
                "Resend email send failed provider=resend sender=%s status=%s body=%s",
                self.from_address,
                exc.code,
                error_body or "<empty>",
            )
            raise RuntimeError(
                f"Resend email send failed with status {exc.code}. {error_body}".strip()
            ) from exc
        except URLError as exc:
            raise RuntimeError("Resend email send failed due to a network error.") from exc

        logger.info("Resend email send success provider=resend recipients=%s subject=%s", to, subject)
        return {
            "provider": "resend",
            "recipient_count": len(to),
            "message_id": data.get("id"),
            "status": "sent",
        }


def _read_error_body(error: HTTPError) -> str:
    try:
        payload = error.read().decode("utf-8").strip()
    except Exception:
        return ""
    return payload
