"""Morning digest job orchestration."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.services.email.email_service import send_digest_email
from backend.app.pipelines.news_pipeline import run_news_ingestion

logger = logging.getLogger(__name__)


def run_morning_digest_job(
    db: Session,
    watchlist_id: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Execute the full morning digest run and email the result."""

    logger.info("Morning digest job started for watchlist_id=%s", watchlist_id)
    pipeline_stats = run_news_ingestion(
        db,
        generate_digest=True,
        digest_watchlist_id=watchlist_id,
    )

    emailed = False
    delivery_status = "pending"
    if pipeline_stats.get("digest_id") is not None:
        delivery_result = send_digest_email(
            db,
            digest_id=pipeline_stats["digest_id"],
            settings=settings or get_settings(),
        )
        emailed = delivery_result["delivery_status"] == "sent"
        delivery_status = delivery_result["delivery_status"]
    result = {
        "fetched_count": pipeline_stats["fetched_count"],
        "inserted_count": pipeline_stats["inserted_count"],
        "cluster_count": pipeline_stats["cluster_count"],
        "summaries_generated": pipeline_stats["summaries_generated"],
        "ranked_count": pipeline_stats["ranked_count"],
        "digest_id": pipeline_stats["digest_id"],
        "emailed": emailed,
        "delivery_status": delivery_status,
    }
    logger.info("Morning digest job completed for watchlist_id=%s result=%s", watchlist_id, result)
    return result
