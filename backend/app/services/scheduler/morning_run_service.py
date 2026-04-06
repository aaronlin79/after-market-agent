"""Morning digest job orchestration."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.services.email.email_service import send_digest_email
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from backend.app.pipelines.news_pipeline import run_news_ingestion

logger = logging.getLogger(__name__)


def run_morning_digest_job(
    db: Session,
    watchlist_id: int,
    settings: Settings | None = None,
    *,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    """Execute the full morning digest run and email the result."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="morning_run",
        watchlist_id=watchlist_id,
        trigger_type=trigger_type,
        provider_used=resolved_settings.news_provider,
    )
    logger.info("Morning digest job started for watchlist_id=%s", watchlist_id)
    try:
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
                settings=resolved_settings,
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
        final_status = "partial_success" if delivery_status != "sent" else "success"
        complete_pipeline_run(db, run, status=final_status, metrics_json=result, provider_used=resolved_settings.news_provider)
        return result
    except Exception as exc:
        fail_pipeline_run(db, run, error=exc, provider_used=resolved_settings.news_provider)
        logger.exception("Morning digest job failed for watchlist_id=%s", watchlist_id)
        raise
