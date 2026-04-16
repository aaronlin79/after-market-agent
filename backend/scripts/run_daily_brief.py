"""Run the full daily brief pipeline headlessly."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.app.core.config import Settings, get_settings
from backend.app.core.db import SessionLocal
from backend.app.models import Digest, Watchlist
from backend.app.pipelines.news_pipeline import run_full_ingestion
from backend.app.services.clustering.clustering_service import cluster_articles
from backend.app.services.digest.digest_service import generate_morning_digest
from backend.app.services.email.email_service import send_digest_email
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from backend.app.services.ranking.ranking_service import rank_clusters
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries
from backend.app.services import watchlist_service

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    settings = get_settings()
    _ensure_sqlite_directory(settings.database_url)
    _validate_settings(settings)
    logger.info(
        "Daily brief configuration database=%s watchlist_target=%s news_provider=%s email_provider=%s",
        _describe_database_url(settings.database_url),
        settings.scheduled_watchlist_id,
        settings.news_provider,
        settings.email_provider,
    )

    db = SessionLocal()
    trigger_type = _resolve_trigger_type()
    watchlist_id: int | None = None
    run = start_pipeline_run(
        db,
        run_type="daily_brief",
        trigger_type=trigger_type,
        provider_used=settings.news_provider,
    )

    try:
        watchlist_id = _resolve_watchlist_id(db, settings)
        business_now = _business_now(settings)
        business_date = business_now.date()
        logger.info(
            "Daily brief run starting watchlist_id=%s trigger_type=%s news_provider=%s email_provider=%s summary_model=%s business_time=%s",
            watchlist_id,
            trigger_type,
            settings.news_provider,
            settings.email_provider,
            settings.openai_model_summary,
            business_now.isoformat(),
        )

        sent_digest = _find_sent_digest_for_business_date(db, watchlist_id, settings)
        if sent_digest is not None:
            result = {
                "watchlist_id": watchlist_id,
                "trigger_type": trigger_type,
                "business_date": business_date.isoformat(),
                "skipped": True,
                "skip_reason": "already_sent_today",
                "digest_id": sent_digest.id,
                "delivery_status": sent_digest.delivery_status,
                "sent_at": sent_digest.sent_at.isoformat() if sent_digest.sent_at else None,
                "email_provider": settings.email_provider,
            }
            logger.info(
                "Daily brief run skipped watchlist_id=%s business_date=%s reason=already_sent_today digest_id=%s",
                watchlist_id,
                business_date.isoformat(),
                sent_digest.id,
            )
            complete_pipeline_run(
                db,
                run,
                status="success",
                metrics_json=result,
                provider_used=settings.news_provider,
            )
            print(json.dumps(result, indent=2))
            return

        ingest_stats = run_full_ingestion(db, watchlist_id=watchlist_id, settings=settings)
        if ingest_stats["news_error"] and ingest_stats["sec_error"]:
            raise RuntimeError("Both news and SEC ingestion failed during the daily brief run.")

        clustering_stats = cluster_articles(db)
        summary_stats = generate_cluster_summaries(db)
        ranking_stats = rank_clusters(db)
        digest_result = generate_morning_digest(db, watchlist_id)
        email_result = send_digest_email(
            db,
            digest_id=digest_result["digest_id"],
            settings=settings,
            trigger_type=trigger_type,
        )

        result = {
            "watchlist_id": watchlist_id,
            "trigger_type": trigger_type,
            "business_date": business_date.isoformat(),
            "skipped": False,
            "news_fetched_count": ingest_stats["news_fetched_count"],
            "news_inserted_count": ingest_stats["news_inserted_count"],
            "filing_fetched_count": ingest_stats["filing_fetched_count"],
            "filing_inserted_count": ingest_stats["filing_inserted_count"],
            "skipped_duplicates": ingest_stats["skipped_duplicates"],
            "news_error": ingest_stats["news_error"],
            "sec_error": ingest_stats["sec_error"],
            "cluster_count": clustering_stats["cluster_count"],
            "representative_count": clustering_stats["representative_count"],
            "summaries_generated": summary_stats["summaries_generated"],
            "ranked_count": ranking_stats["ranked_count"],
            "digest_id": digest_result["digest_id"],
            "surfaced_item_count": digest_result["surfaced_item_count"],
            "delivery_status": email_result["delivery_status"],
            "emailed": email_result["delivery_status"] == "sent",
            "provider_used": settings.news_provider,
            "email_provider": email_result["provider"],
        }
        complete_pipeline_run(
            db,
            run,
            status="partial_success" if ingest_stats["news_error"] or ingest_stats["sec_error"] else "success",
            metrics_json=result,
            provider_used=settings.news_provider,
        )
        logger.info("Daily brief run completed result=%s", result)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        fail_pipeline_run(
            db,
            run,
            error=exc,
            metrics_json={"watchlist_id": watchlist_id, "trigger_type": trigger_type},
            provider_used=settings.news_provider,
        )
        logger.exception("Daily brief run failed.")
        raise
    finally:
        db.close()


def _validate_settings(settings: Settings) -> None:
    missing: list[str] = []

    if not settings.digest_recipients:
        missing.append("DIGEST_RECIPIENTS")
    if settings.news_provider.lower().strip() == "finnhub" and not settings.news_api_key:
        missing.append("NEWS_API_KEY")
    if not settings.sec_user_agent:
        missing.append("SEC_USER_AGENT")
    if settings.email_provider.lower().strip() == "brevo":
        if not settings.brevo_api_key:
            missing.append("BREVO_API_KEY")
        if not settings.email_from:
            missing.append("EMAIL_FROM")
    if settings.email_provider.lower().strip() == "resend":
        if not settings.resend_api_key:
            missing.append("RESEND_API_KEY")
        if not settings.email_from:
            missing.append("EMAIL_FROM")
    if settings.openai_api_key is None or not settings.openai_api_key.strip():
        logger.warning("OPENAI_API_KEY is not configured. Cluster summaries may fall back to baseline.")

    if missing:
        raise RuntimeError(f"Missing required configuration for daily brief run: {', '.join(sorted(set(missing)))}")


def _resolve_trigger_type() -> str:
    event_name = getenv("GITHUB_EVENT_NAME", "").strip().lower()
    if event_name == "schedule":
        return "scheduled"
    return "manual"


def _business_now(settings: Settings) -> datetime:
    return datetime.now(ZoneInfo(settings.digest_timezone))


def _find_sent_digest_for_business_date(db, watchlist_id: int, settings: Settings) -> Digest | None:
    business_date = _business_now(settings).date()
    digests = db.execute(
        select(Digest)
        .where(Digest.watchlist_id == watchlist_id, Digest.sent_at.is_not(None))
        .order_by(Digest.sent_at.desc(), Digest.id.desc())
    ).scalars()

    for digest in digests:
        if digest.sent_at is None:
            continue
        sent_at = digest.sent_at.astimezone(ZoneInfo(settings.digest_timezone))
        if sent_at.date() == business_date:
            return digest
    return None


def _resolve_watchlist_id(db, settings: Settings) -> int:
    logger.info(
        "Resolving scheduled watchlist target_id=%s database=%s",
        settings.scheduled_watchlist_id,
        _describe_database_url(settings.database_url),
    )
    watchlist = db.execute(select(Watchlist).where(Watchlist.id == settings.scheduled_watchlist_id)).scalar_one_or_none()
    if watchlist is not None:
        logger.info(
            "Resolved watchlist directly by id watchlist_id=%s name=%s",
            watchlist.id,
            watchlist.name,
        )
    else:
        available_watchlists = list(db.execute(select(Watchlist).order_by(Watchlist.id.asc())).scalars())
        logger.warning(
            "Configured watchlist was not found target_id=%s available_watchlists=%s fallback_seeding_triggered=false",
            settings.scheduled_watchlist_id,
            [{"id": item.id, "name": item.name} for item in available_watchlists],
        )
        if len(available_watchlists) == 1:
            watchlist = available_watchlists[0]
            logger.warning(
                "Using the only persisted watchlist instead of seeding a default watchlist watchlist_id=%s name=%s",
                watchlist.id,
                watchlist.name,
            )
        else:
            raise RuntimeError(
                "Scheduled watchlist was not found and no unambiguous persisted watchlist is available. "
                "Set SCHEDULED_WATCHLIST_ID to an existing watchlist id in the active database."
            )

    hydrated_watchlist = watchlist_service.get_watchlist(db, watchlist.id)
    if not hydrated_watchlist.symbols:
        raise RuntimeError(
            f"Watchlist {hydrated_watchlist.id} has no symbols. Add symbols before running the daily brief."
        )

    logger.info(
        "Final watchlist selection watchlist_id=%s name=%s symbols=%s",
        hydrated_watchlist.id,
        hydrated_watchlist.name,
        [symbol.symbol for symbol in hydrated_watchlist.symbols],
    )

    return hydrated_watchlist.id


def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    path_value = database_url.removeprefix("sqlite:///")
    if not path_value or path_value == ":memory:":
        return

    sqlite_path = Path(path_value)
    if not sqlite_path.is_absolute():
        sqlite_path = Path.cwd() / sqlite_path

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def _describe_database_url(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        path_value = database_url.removeprefix("sqlite:///")
        sqlite_path = Path(path_value)
        if not sqlite_path.is_absolute():
            sqlite_path = (Path.cwd() / sqlite_path).resolve()
        return f"sqlite:///{sqlite_path}"
    if "://" not in database_url:
        return "<unknown>"
    scheme = database_url.split("://", 1)[0]
    return f"{scheme}://<redacted>"


if __name__ == "__main__":
    main()
