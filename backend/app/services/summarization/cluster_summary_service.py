"""Cluster summary generation service."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import ClusterSummary, SourceItem
from backend.app.services.summarization.summarization_service import summarize_cluster

logger = logging.getLogger(__name__)


def generate_cluster_summaries(db: Session) -> dict[str, int]:
    """Generate summaries for clustered articles that do not yet have one."""

    cluster_ids = list(
        db.execute(
            select(SourceItem.cluster_id)
            .where(SourceItem.cluster_id.is_not(None))
            .group_by(SourceItem.cluster_id)
            .order_by(SourceItem.cluster_id.asc())
        ).scalars()
    )

    if not cluster_ids:
        logger.info("Cluster summarization skipped because no clusters were found.")
        return {"clusters_processed": 0, "summaries_generated": 0, "skipped_clusters": 0}

    existing_summary_cluster_ids = set(
        db.execute(select(ClusterSummary.cluster_id).where(ClusterSummary.cluster_id.in_(cluster_ids))).scalars()
    )

    summaries_generated = 0
    skipped_clusters = 0

    for cluster_id in cluster_ids:
        if cluster_id in existing_summary_cluster_ids:
            skipped_clusters += 1
            continue

        articles = list(
            db.execute(
                select(SourceItem)
                .where(SourceItem.cluster_id == cluster_id)
                .order_by(SourceItem.is_representative.desc(), SourceItem.published_at.asc(), SourceItem.id.asc())
            ).scalars()
        )
        if not articles:
            skipped_clusters += 1
            continue

        summary_text = summarize_cluster(articles)
        if not summary_text:
            skipped_clusters += 1
            continue

        db.add(ClusterSummary(cluster_id=cluster_id, summary_text=summary_text))
        summaries_generated += 1

    db.commit()
    logger.info(
        "Cluster summarization complete: processed=%s generated=%s skipped=%s",
        len(cluster_ids),
        summaries_generated,
        skipped_clusters,
    )
    return {
        "clusters_processed": len(cluster_ids),
        "summaries_generated": summaries_generated,
        "skipped_clusters": skipped_clusters,
    }


def list_cluster_summaries(db: Session) -> list[dict[str, int | str]]:
    """Return stored cluster summaries with article counts."""

    rows = db.execute(
        select(
            ClusterSummary.cluster_id,
            ClusterSummary.summary_text,
            func.count(SourceItem.id).label("article_count"),
        )
        .outerjoin(SourceItem, SourceItem.cluster_id == ClusterSummary.cluster_id)
        .group_by(ClusterSummary.id, ClusterSummary.cluster_id, ClusterSummary.summary_text)
        .order_by(ClusterSummary.cluster_id.asc())
    ).all()

    return [
        {
            "cluster_id": cluster_id,
            "summary_text": summary_text,
            "article_count": article_count,
        }
        for cluster_id, summary_text, article_count in rows
    ]
