"""News ingestion pipeline."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import WatchlistSymbol
from backend.app.services.clustering.clustering_service import cluster_articles
from backend.app.services.digest.digest_service import generate_morning_digest
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.news_ingestion_service import ingest_news
from backend.app.services.ranking.ranking_service import rank_clusters
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries

logger = logging.getLogger(__name__)


def run_news_ingestion(
    db: Session,
    adapter: BaseNewsAdapter | None = None,
    *,
    generate_digest: bool = False,
    digest_watchlist_id: int | None = None,
) -> dict[str, Any]:
    """Run the news ingestion pipeline for all watchlist symbols."""

    symbols = list(
        db.execute(select(WatchlistSymbol.symbol).order_by(WatchlistSymbol.symbol.asc())).scalars().all()
    )
    unique_symbols = sorted(set(symbols))
    logger.info("Running news pipeline for symbols: %s", unique_symbols)

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=24)

    ingestion_stats = ingest_news(
        db=db,
        symbols=unique_symbols,
        start_time=start_time,
        end_time=end_time,
        adapter=adapter,
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

    return {
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
