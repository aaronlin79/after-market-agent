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
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from backend.app.services.email.resend_provider import ResendEmailProvider

logger = logging.getLogger(__name__)


def send_digest_email(
    db: Session,
    digest_id: int,
    settings: Settings | None = None,
    *,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    """Send a digest using the configured email provider."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="email_send",
        trigger_type=trigger_type,
        provider_used=resolved_settings.email_provider,
        metrics_json={"digest_id": digest_id},
    )
    digest = db.execute(select(Digest).where(Digest.id == digest_id)).scalar_one_or_none()
    if digest is None:
        error = ValueError(f"Digest {digest_id} was not found.")
        fail_pipeline_run(db, run, error=error, provider_used=resolved_settings.email_provider)
        raise error

    recipients = resolved_settings.digest_recipients
    if not recipients:
        error = ValueError("DIGEST_RECIPIENTS must contain at least one email recipient.")
        fail_pipeline_run(db, run, error=error, provider_used=resolved_settings.email_provider)
        raise error

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
    except Exception as exc:
        digest.delivery_status = "failed"
        db.add(digest)
        db.commit()
        logger.exception("Digest email send failed for digest_id=%s", digest_id)
        fail_pipeline_run(
            db,
            run,
            error=exc,
            metrics_json={"digest_id": digest_id, "recipient_count": len(recipients)},
            provider_used=resolved_settings.email_provider,
        )
        raise

    digest.delivery_status = "sent"
    digest.sent_at = datetime.now(UTC)
    db.add(digest)
    db.commit()
    db.refresh(digest)

    payload = {
        "digest_id": digest.id,
        "delivery_status": digest.delivery_status,
        "recipient_count": result["recipient_count"],
        "provider": result["provider"],
        "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
        "message_id": result.get("message_id"),
    }
    complete_pipeline_run(db, run, metrics_json=payload, provider_used=resolved_settings.email_provider)
    return payload


def _get_email_provider(settings: Settings) -> BaseEmailProvider:
    provider_name = settings.email_provider.lower().strip()
    if provider_name == "mock":
        return MockEmailProvider()
    if provider_name == "resend":
        return ResendEmailProvider(api_key=settings.email_api_key or "", from_address=settings.email_from)
    raise ValueError(f"Unsupported EMAIL_PROVIDER: {settings.email_provider}")
