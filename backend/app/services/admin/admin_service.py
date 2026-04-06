"""Read-only admin inspection helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import ClusterSummary, Digest, DigestEntry, PipelineRun, SourceItem, StoryCluster
from backend.app.services.digest.digest_service import list_digests
from backend.app.services.observability.pipeline_tracker import calculate_duration_ms
from backend.app.services.summarization.cluster_summary_service import list_cluster_summaries


def list_pipeline_runs(db: Session) -> list[dict[str, Any]]:
    runs = list(
        db.execute(select(PipelineRun).order_by(PipelineRun.started_at.desc(), PipelineRun.id.desc())).scalars()
    )
    return [
        {
            "id": run.id,
            "run_type": run.run_type,
            "status": run.status,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "duration_ms": calculate_duration_ms(run),
            "watchlist_id": run.watchlist_id,
            "trigger_type": run.trigger_type,
            "provider_used": run.provider_used,
        }
        for run in runs
    ]


def get_pipeline_run(db: Session, run_id: int) -> dict[str, Any] | None:
    run = db.execute(select(PipelineRun).where(PipelineRun.id == run_id)).scalar_one_or_none()
    if run is None:
        return None
    return {
        "id": run.id,
        "run_type": run.run_type,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "duration_ms": calculate_duration_ms(run),
        "watchlist_id": run.watchlist_id,
        "trigger_type": run.trigger_type,
        "provider_used": run.provider_used,
        "error_message": run.error_message,
        "metrics_json": run.metrics_json,
    }


def list_source_items(
    db: Session,
    *,
    source_type: str | None = None,
    symbol: str | None = None,
    cluster_id: str | None = None,
) -> list[dict[str, Any]]:
    items = list(
        db.execute(
            select(SourceItem).order_by(SourceItem.published_at.desc(), SourceItem.id.desc())
        ).scalars()
    )
    normalized_symbol = symbol.strip().upper() if symbol else None
    if source_type is not None:
        items = [item for item in items if item.source_type == source_type]
    if cluster_id is not None:
        items = [item for item in items if item.cluster_id == cluster_id]
    if normalized_symbol is not None:
        items = [item for item in items if _item_matches_symbol(item, normalized_symbol)]

    return [
        {
            "id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "source_name": item.source_name,
            "published_at": item.published_at.isoformat(),
            "cluster_id": item.cluster_id,
            "is_representative": item.is_representative,
        }
        for item in items
    ]


def get_source_item(db: Session, source_item_id: int) -> dict[str, Any] | None:
    item = db.execute(select(SourceItem).where(SourceItem.id == source_item_id)).scalar_one_or_none()
    if item is None:
        return None
    return {
        "id": item.id,
        "source_type": item.source_type,
        "source_name": item.source_name,
        "external_id": item.external_id,
        "url": item.url,
        "title": item.title,
        "body_text": item.body_text,
        "published_at": item.published_at.isoformat(),
        "fetched_at": item.fetched_at.isoformat(),
        "content_hash": item.content_hash,
        "cluster_id": item.cluster_id,
        "is_representative": item.is_representative,
        "metadata_json": item.metadata_json,
    }


def list_admin_clusters(db: Session, *, sort_by: str = "importance") -> list[dict[str, Any]]:
    clusters = list(
        db.execute(select(StoryCluster).options(selectinload(StoryCluster.digest_entries))).scalars()
    )
    article_counts = _article_counts(db)
    if sort_by == "newest":
        clusters.sort(key=lambda cluster: (cluster.last_seen_at, cluster.id), reverse=True)
    else:
        clusters.sort(key=lambda cluster: (cluster.importance_score, cluster.last_seen_at, cluster.id), reverse=True)

    return [
        {
            "id": cluster.id,
            "cluster_id": cluster.cluster_key,
            "representative_title": cluster.representative_title,
            "primary_symbol": cluster.primary_symbol,
            "importance_score": cluster.importance_score,
            "confidence": cluster.confidence,
            "event_type": cluster.event_type,
            "article_count": article_counts.get(cluster.cluster_key, 0),
        }
        for cluster in clusters
    ]


def get_admin_cluster_detail(db: Session, cluster_key: str) -> dict[str, Any] | None:
    cluster = db.execute(
        select(StoryCluster)
        .options(selectinload(StoryCluster.digest_entries))
        .where(StoryCluster.cluster_key == cluster_key)
    ).scalar_one_or_none()
    if cluster is None:
        return None

    items = list(
        db.execute(
            select(SourceItem)
            .where(SourceItem.cluster_id == cluster_key)
            .order_by(SourceItem.is_representative.desc(), SourceItem.published_at.asc(), SourceItem.id.asc())
        ).scalars()
    )
    summary = db.execute(select(ClusterSummary).where(ClusterSummary.cluster_id == cluster_key)).scalar_one_or_none()
    representative_item = next((item for item in items if item.is_representative), None)
    digest_sections = [
        {
            "digest_id": entry.digest_id,
            "section_name": entry.section_name,
            "rank": entry.rank,
            "rationale_json": entry.rationale_json,
        }
        for entry in sorted(cluster.digest_entries, key=lambda entry: (entry.digest_id, entry.rank))
    ]

    return {
        "id": cluster.id,
        "cluster_id": cluster.cluster_key,
        "representative_title": cluster.representative_title,
        "primary_symbol": cluster.primary_symbol,
        "importance_score": cluster.importance_score,
        "novelty_score": cluster.novelty_score,
        "credibility_score": cluster.credibility_score,
        "event_type": cluster.event_type,
        "confidence": cluster.confidence,
        "first_seen_at": cluster.first_seen_at.isoformat(),
        "last_seen_at": cluster.last_seen_at.isoformat(),
        "article_count": len(items),
        "source_items": [
            {
                "id": item.id,
                "title": item.title,
                "source_type": item.source_type,
                "source_name": item.source_name,
                "published_at": item.published_at.isoformat(),
                "is_representative": item.is_representative,
            }
            for item in items
        ],
        "representative_item": (
            {
                "id": representative_item.id,
                "title": representative_item.title,
                "source_name": representative_item.source_name,
                "published_at": representative_item.published_at.isoformat(),
            }
            if representative_item is not None
            else None
        ),
        "summary": (
            {
                "cluster_id": summary.cluster_id,
                "summary_text": summary.summary_text,
                "model_name": summary.model_name,
                "prompt_version": summary.prompt_version,
                "created_at": summary.created_at.isoformat(),
            }
            if summary is not None
            else None
        ),
        "digest_sections": digest_sections,
    }


def list_admin_summaries(db: Session) -> list[dict[str, Any]]:
    summaries = list_cluster_summaries(db)
    summary_rows = {
        summary.cluster_id: summary
        for summary in db.execute(select(ClusterSummary).order_by(ClusterSummary.created_at.desc())).scalars()
    }
    return [
        {
            **item,
            "created_at": summary_rows[item["cluster_id"]].created_at.isoformat(),
        }
        for item in summaries
        if item["cluster_id"] in summary_rows
    ]


def list_admin_digests(db: Session) -> list[dict[str, Any]]:
    return list_digests(db)


def _article_counts(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in db.execute(select(SourceItem.cluster_id).where(SourceItem.cluster_id.is_not(None))).scalars():
        counts[item] = counts.get(item, 0) + 1
    return counts


def _item_matches_symbol(item: SourceItem, symbol: str) -> bool:
    metadata = item.metadata_json or {}
    if metadata.get("ticker") == symbol or metadata.get("symbol") == symbol:
        return True
    symbols = metadata.get("symbols", [])
    return isinstance(symbols, list) and symbol in {str(value).strip().upper() for value in symbols}
