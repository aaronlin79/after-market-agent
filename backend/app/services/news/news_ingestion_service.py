"""Service for fetching and storing news items."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import SourceItem
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.adapters.mock_adapter import MockNewsAdapter
from backend.app.services.news.normalizer import normalize_news_item

logger = logging.getLogger(__name__)


def ingest_news(
    db: Session,
    symbols: list[str],
    start_time: datetime,
    end_time: datetime,
    adapter: BaseNewsAdapter | None = None,
) -> dict[str, int]:
    """Fetch, normalize, deduplicate, and store raw news items."""

    normalized_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not normalized_symbols:
        logger.info("No symbols provided for news ingestion.")
        return {"fetched_count": 0, "inserted_count": 0, "skipped_duplicates": 0}

    adapter_instance = adapter or MockNewsAdapter()
    logger.info("Fetching news for symbols: %s", normalized_symbols)
    fetched_items = adapter_instance.fetch_news(normalized_symbols, start_time, end_time)
    logger.info("Fetched %s raw news items.", len(fetched_items))

    inserted_count = 0
    skipped_duplicates = 0
    seen_hashes: set[str] = set()

    for raw_item in fetched_items:
        normalized_item = normalize_news_item(raw_item)
        content_hash = compute_content_hash(normalized_item["title"], normalized_item["url"])

        if content_hash in seen_hashes or _source_item_exists(db, content_hash):
            skipped_duplicates += 1
            continue

        seen_hashes.add(content_hash)
        source_item = SourceItem(
            source_type="news",
            source_name=normalized_item["source_name"],
            external_id=normalized_item["external_id"],
            url=normalized_item["url"],
            title=normalized_item["title"],
            body_text=normalized_item["body_text"],
            published_at=normalized_item["published_at"],
            fetched_at=datetime.now(UTC),
            content_hash=content_hash,
            metadata_json=normalized_item["metadata_json"],
        )
        db.add(source_item)
        inserted_count += 1

    db.commit()
    logger.info(
        "News ingestion complete for symbols=%s fetched=%s inserted=%s duplicates=%s",
        normalized_symbols,
        len(fetched_items),
        inserted_count,
        skipped_duplicates,
    )
    return {
        "fetched_count": len(fetched_items),
        "inserted_count": inserted_count,
        "skipped_duplicates": skipped_duplicates,
    }


def compute_content_hash(title: str, url: str) -> str:
    """Compute a stable content hash from title and URL."""

    value = f"{title.strip().lower()}::{url.strip().lower()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_item_exists(db: Session, content_hash: str) -> bool:
    """Return whether a source item already exists for a hash."""

    statement = select(SourceItem.id).where(SourceItem.content_hash == content_hash)
    return db.execute(statement).scalar_one_or_none() is not None
