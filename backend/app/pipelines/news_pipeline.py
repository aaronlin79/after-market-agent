"""News ingestion pipeline."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import WatchlistSymbol
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.news_ingestion_service import ingest_news

logger = logging.getLogger(__name__)


def run_news_ingestion(
    db: Session,
    adapter: BaseNewsAdapter | None = None,
) -> dict[str, int]:
    """Run the news ingestion pipeline for all watchlist symbols."""

    symbols = list(
        db.execute(select(WatchlistSymbol.symbol).order_by(WatchlistSymbol.symbol.asc())).scalars().all()
    )
    unique_symbols = sorted(set(symbols))
    logger.info("Running news pipeline for symbols: %s", unique_symbols)

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=24)

    return ingest_news(
        db=db,
        symbols=unique_symbols,
        start_time=start_time,
        end_time=end_time,
        adapter=adapter,
    )
