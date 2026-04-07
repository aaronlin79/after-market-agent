"""News ingestion pipeline."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models import WatchlistSymbol
from backend.app.services.clustering.clustering_service import cluster_articles
from backend.app.services.digest.digest_service import generate_morning_digest
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.news_ingestion_service import ingest_news
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from backend.app.services.ranking.ranking_service import rank_clusters
from backend.app.services.sec.sec_ingestion_service import get_watchlist_symbols, ingest_sec_filings
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries

logger = logging.getLogger(__name__)


def run_news_ingestion(
    db: Session,
    adapter: BaseNewsAdapter | None = None,
    *,
    generate_digest: bool = False,
    digest_watchlist_id: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run the news ingestion pipeline for all watchlist symbols."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="news_pipeline",
        trigger_type="manual",
        provider_used=resolved_settings.news_provider,
    )
    symbols = list(
        db.execute(select(WatchlistSymbol.symbol).order_by(WatchlistSymbol.symbol.asc())).scalars().all()
    )
    unique_symbols = sorted(set(symbols))
    logger.info("Running news pipeline for symbols: %s", unique_symbols)

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=resolved_settings.ingestion_lookback_hours)

    try:
        ingestion_stats = ingest_news(
            db=db,
            symbols=unique_symbols,
            start_time=start_time,
            end_time=end_time,
            adapter=adapter,
            settings=resolved_settings,
        )
        clustering_stats = cluster_articles(db)
        summary_stats = generate_cluster_summaries(db)
        ranking_stats = rank_clusters(db)
        digest_generated = False
        digest_id: int | None = None
        surfaced_item_count = 0

        if generate_digest and digest_watchlist_id is not None:
            digest_result = generate_morning_digest(db, digest_watchlist_id)
            digest_generated = True
            digest_id = digest_result["digest_id"]
            surfaced_item_count = digest_result["surfaced_item_count"]

        result = {
            **ingestion_stats,
            "cluster_count": clustering_stats["cluster_count"],
            "representative_count": clustering_stats["representative_count"],
            "summaries_generated": summary_stats["summaries_generated"],
            "clusters_processed": summary_stats["clusters_processed"],
            "openai_calls_made": summary_stats["openai_calls_made"],
            "fallback_count": summary_stats["fallback_count"],
            "skipped_due_to_limits": summary_stats["skipped_due_to_limits"],
            "ranked_count": ranking_stats["ranked_count"],
            "digest_generated": digest_generated,
            "digest_id": digest_id,
            "surfaced_item_count": surfaced_item_count,
        }
        complete_pipeline_run(db, run, metrics_json=result, provider_used=ingestion_stats["provider_used"])
        return result
    except Exception as exc:
        fail_pipeline_run(db, run, error=exc, provider_used=resolved_settings.news_provider)
        logger.exception("News pipeline failed for symbols=%s", unique_symbols)
        raise


def run_sec_pipeline(
    db: Session,
    *,
    watchlist_id: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run SEC filings ingestion only."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="sec_pipeline",
        watchlist_id=watchlist_id,
        trigger_type="manual",
        provider_used="sec",
    )
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=resolved_settings.ingestion_lookback_hours)
    symbols = get_watchlist_symbols(db, watchlist_id=watchlist_id)
    logger.info("Running SEC ingestion for watchlist_id=%s symbols=%s", watchlist_id, sorted(set(symbols)))
    try:
        result = {
            "watchlist_id": watchlist_id,
            **ingest_sec_filings(
                db=db,
                symbols=symbols,
                start_time=start_time,
                end_time=end_time,
                settings=resolved_settings,
            ),
        }
        complete_pipeline_run(db, run, metrics_json=result, provider_used="sec")
        return result
    except Exception as exc:
        fail_pipeline_run(db, run, error=exc, provider_used="sec")
        logger.exception("SEC pipeline failed watchlist_id=%s", watchlist_id)
        raise


def run_full_ingestion(
    db: Session,
    *,
    watchlist_id: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run news and SEC ingestion together with partial failure handling."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="full_ingest",
        watchlist_id=watchlist_id,
        trigger_type="manual",
        provider_used=resolved_settings.news_provider,
    )
    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=resolved_settings.ingestion_lookback_hours)
    symbols = get_watchlist_symbols(db, watchlist_id=watchlist_id)
    unique_symbols = sorted(set(symbols))
    logger.info("Running full ingestion for watchlist_id=%s symbols=%s", watchlist_id, unique_symbols)

    news_error: str | None = None
    sec_error: str | None = None
    news_stats = {
        "provider_used": resolved_settings.news_provider,
        "fetched_count": 0,
        "inserted_count": 0,
        "skipped_duplicates": 0,
    }
    filing_stats = {
        "provider_used": "sec",
        "mapped_symbol_count": 0,
        "fetched_count": 0,
        "inserted_count": 0,
        "skipped_duplicates": 0,
    }

    try:
        news_stats = ingest_news(
            db=db,
            symbols=unique_symbols,
            start_time=start_time,
            end_time=end_time,
            settings=resolved_settings,
        )
    except Exception as exc:
        news_error = f"{type(exc).__name__}: {exc}"
        logger.exception("News ingestion failed during full ingest watchlist_id=%s", watchlist_id)

    try:
        filing_stats = ingest_sec_filings(
            db=db,
            symbols=unique_symbols,
            start_time=start_time,
            end_time=end_time,
            settings=resolved_settings,
        )
    except Exception as exc:
        sec_error = f"{type(exc).__name__}: {exc}"
        logger.exception("SEC ingestion failed during full ingest watchlist_id=%s", watchlist_id)

    result = {
        "watchlist_id": watchlist_id,
        "provider_used": news_stats["provider_used"],
        "news_fetched_count": news_stats["fetched_count"],
        "news_inserted_count": news_stats["inserted_count"],
        "filing_fetched_count": filing_stats["fetched_count"],
        "filing_inserted_count": filing_stats["inserted_count"],
        "skipped_duplicates": news_stats["skipped_duplicates"] + filing_stats["skipped_duplicates"],
        "news_error": news_error,
        "sec_error": sec_error,
    }
    final_status = "partial_success" if news_error or sec_error else "success"
    try:
        complete_pipeline_run(db, run, status=final_status, metrics_json=result, provider_used=news_stats["provider_used"])
        return result
    except Exception as exc:
        fail_pipeline_run(db, run, error=exc, metrics_json=result, provider_used=news_stats["provider_used"])
        logger.exception("Full ingestion completion failed watchlist_id=%s", watchlist_id)
        raise
