"""Service for fetching and storing news items."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models import SourceItem
from backend.app.services.news.adapters import get_news_adapter
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.normalizer import normalize_news_item
from backend.app.services.observability.pipeline_tracker import fail_pipeline_run, start_pipeline_run, complete_pipeline_run

logger = logging.getLogger(__name__)


def ingest_news(
    db: Session,
    symbols: list[str],
    start_time: datetime,
    end_time: datetime,
    adapter: BaseNewsAdapter | None = None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Fetch, normalize, deduplicate, and store raw news items."""

    resolved_settings = settings or get_settings()
    run = start_pipeline_run(
        db,
        run_type="news_ingestion",
        trigger_type="manual",
        provider_used=resolved_settings.news_provider,
        metrics_json={"symbol_count": len(symbols)},
    )
    normalized_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not normalized_symbols:
        logger.info("No symbols provided for news ingestion.")
        stats = {
            "provider_used": resolved_settings.news_provider,
            "fetched_count": 0,
            "inserted_count": 0,
            "skipped_duplicates": 0,
        }
        complete_pipeline_run(db, run, metrics_json=stats, provider_used=resolved_settings.news_provider)
        return stats

    try:
        adapter_instance = adapter or get_news_adapter(resolved_settings)
        provider_used = type(adapter_instance).__name__.replace("NewsAdapter", "").replace("Adapter", "").lower() or "news"
        logger.info("Fetching news for symbols=%s provider=%s", normalized_symbols, provider_used)
        fetched_items = adapter_instance.fetch_news(normalized_symbols, start_time, end_time)
        logger.info("Fetched %s raw news items from provider=%s.", len(fetched_items), provider_used)

        normalized_items = [normalize_news_item(raw_item) for raw_item in fetched_items]
        stats = store_source_items(db, normalized_items, source_type="news")

        logger.info(
            "News ingestion complete for symbols=%s provider=%s fetched=%s inserted=%s duplicates=%s",
            normalized_symbols,
            provider_used,
            stats["fetched_count"],
            stats["inserted_count"],
            stats["skipped_duplicates"],
        )
        final_stats = {"provider_used": provider_used, **stats}
        complete_pipeline_run(db, run, metrics_json=final_stats, provider_used=provider_used)
        return final_stats
    except Exception as exc:
        fail_pipeline_run(
            db,
            run,
            error=exc,
            metrics_json={"symbol_count": len(normalized_symbols)},
            provider_used=resolved_settings.news_provider,
        )
        logger.exception("News ingestion failed for symbols=%s", normalized_symbols)
        raise


def compute_content_hash(title: str, url: str) -> str:
    """Compute a stable content hash from title and URL."""

    value = f"{title.strip().lower()}::{url.strip().lower()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def store_source_items(
    db: Session,
    items: list[dict[str, Any]],
    *,
    source_type: str,
) -> dict[str, int]:
    """Store normalized source items with duplicate protection."""

    inserted_count = 0
    skipped_duplicates = 0
    seen_hashes: set[str] = set()

    for item in items:
        content_hash = str(item.get("content_hash") or compute_content_hash(item["title"], item["url"]))
        external_id = str(item["external_id"]).strip() if item.get("external_id") is not None else None
        source_name = str(item["source_name"]).strip()

        if content_hash in seen_hashes or _source_item_exists(
            db,
            content_hash=content_hash,
            source_type=source_type,
            source_name=source_name,
            external_id=external_id,
        ):
            skipped_duplicates += 1
            continue

        seen_hashes.add(content_hash)

        db.add(
            SourceItem(
                source_type=source_type,
                source_name=source_name,
                external_id=external_id,
                url=str(item["url"]).strip(),
                title=str(item["title"]).strip(),
                body_text=str(item["body_text"]).strip(),
                published_at=item["published_at"],
                fetched_at=datetime.now(UTC),
                content_hash=content_hash,
                metadata_json=item.get("metadata_json"),
            )
        )
        inserted_count += 1

    db.commit()
    return {
        "fetched_count": len(items),
        "inserted_count": inserted_count,
        "skipped_duplicates": skipped_duplicates,
    }


def _source_item_exists(
    db: Session,
    *,
    content_hash: str,
    source_type: str,
    source_name: str,
    external_id: str | None,
) -> bool:
    """Return whether a source item already exists for a hash or external id."""

    if db.execute(select(SourceItem.id).where(SourceItem.content_hash == content_hash)).scalar_one_or_none() is not None:
        return True
    if external_id is None:
        return False
    statement = select(SourceItem.id).where(
        SourceItem.source_type == source_type,
        SourceItem.source_name == source_name,
        SourceItem.external_id == external_id,
    )
    return db.execute(statement).scalar_one_or_none() is not None
