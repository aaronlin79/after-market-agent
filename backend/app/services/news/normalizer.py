"""Helpers for normalizing incoming news items."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


REQUIRED_FIELDS = ("title", "url", "source_name", "published_at")


def normalize_news_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw news item into a storage-ready payload."""

    for field_name in REQUIRED_FIELDS:
        value = item.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError(f"Missing required field: {field_name}")

    title = str(item["title"]).strip()
    body_text = str(item.get("body_text") or "").strip() or title
    url = str(item["url"]).strip()
    source_name = str(item["source_name"]).strip()
    external_id = item.get("external_id")
    metadata_json = item.get("metadata_json")
    published_at = ensure_utc(item["published_at"])

    return {
        "external_id": str(external_id).strip() if external_id is not None else None,
        "title": title,
        "body_text": body_text,
        "url": url,
        "source_name": source_name,
        "published_at": published_at,
        "metadata_json": metadata_json,
    }


def ensure_utc(value: datetime) -> datetime:
    """Return a UTC-aware datetime."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
