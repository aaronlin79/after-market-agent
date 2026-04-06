"""Email sending orchestration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models import Digest
from backend.app.services.email.base import BaseEmailProvider
from backend.app.services.email.mock_provider import MockEmailProvider
from backend.app.services.email.resend_provider import ResendEmailProvider

logger = logging.getLogger(__name__)


def send_digest_email(
    db: Session,
    digest_id: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Send a digest using the configured email provider."""

    digest = db.execute(select(Digest).where(Digest.id == digest_id)).scalar_one_or_none()
    if digest is None:
        raise ValueError(f"Digest {digest_id} was not found.")

    resolved_settings = settings or get_settings()
    recipients = resolved_settings.digest_recipients
    if not recipients:
        raise ValueError("DIGEST_RECIPIENTS must contain at least one email recipient.")

    provider = _get_email_provider(resolved_settings)
    logger.info(
        "Sending digest email digest_id=%s recipients=%s provider=%s",
        digest_id,
        recipients,
        resolved_settings.email_provider,
    )

    try:
        result = provider.send_email(
            to=recipients,
            subject=digest.subject_line,
            html=digest.digest_html,
            text=digest.digest_markdown,
        )
    except Exception:
        digest.delivery_status = "failed"
        db.add(digest)
        db.commit()
        logger.exception("Digest email send failed for digest_id=%s", digest_id)
        raise

    digest.delivery_status = "sent"
    digest.sent_at = datetime.now(UTC)
    db.add(digest)
    db.commit()
    db.refresh(digest)

    return {
        "digest_id": digest.id,
        "delivery_status": digest.delivery_status,
        "recipient_count": result["recipient_count"],
        "provider": result["provider"],
        "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
        "message_id": result.get("message_id"),
    }


def _get_email_provider(settings: Settings) -> BaseEmailProvider:
    provider_name = settings.email_provider.lower().strip()
    if provider_name == "mock":
        return MockEmailProvider()
    if provider_name == "resend":
        return ResendEmailProvider(api_key=settings.email_api_key or "", from_address=settings.email_from)
    raise ValueError(f"Unsupported EMAIL_PROVIDER: {settings.email_provider}")
