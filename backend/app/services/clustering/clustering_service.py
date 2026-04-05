"""Article clustering service."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import SourceItem
from backend.app.services.clustering.similarity import cosine_similarity
from backend.app.services.embeddings.embedding_service import generate_embedding

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.5


@dataclass(frozen=True)
class ClusterStats:
    """Summary of a clustering run."""

    article_count: int
    cluster_count: int
    representative_count: int

    def to_dict(self) -> dict[str, int]:
        """Convert stats to a plain dictionary."""

        return {
            "article_count": self.article_count,
            "cluster_count": self.cluster_count,
            "representative_count": self.representative_count,
        }


def cluster_articles(
    db: Session,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, int]:
    """Cluster recent source items using deterministic local embeddings."""

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    articles = list(
        db.execute(
            select(SourceItem)
            .where(SourceItem.source_type == "news", SourceItem.published_at >= cutoff)
            .order_by(SourceItem.published_at.asc(), SourceItem.id.asc())
        ).scalars()
    )

    article_count = len(articles)
    if article_count == 0:
        logger.info("Clustering skipped because no recent articles were found.")
        return ClusterStats(article_count=0, cluster_count=0, representative_count=0).to_dict()

    embeddings = {
        article.id: generate_embedding(f"{article.title} {article.body_text}")
        for article in articles
    }
    parent = {article.id: article.id for article in articles}

    for left_index, left_article in enumerate(articles):
        for right_article in articles[left_index + 1 :]:
            similarity = cosine_similarity(
                embeddings[left_article.id],
                embeddings[right_article.id],
            )
            if similarity >= similarity_threshold:
                _union(parent, left_article.id, right_article.id)

    grouped_articles: dict[int, list[SourceItem]] = defaultdict(list)
    for article in articles:
        grouped_articles[_find(parent, article.id)].append(article)

    for cluster_articles_list in grouped_articles.values():
        cluster_articles_list.sort(key=lambda item: (item.published_at, item.id))
        cluster_identifier = f"cluster-{min(item.id for item in cluster_articles_list)}"
        representative = _select_representative(cluster_articles_list)

        for article in cluster_articles_list:
            article.cluster_id = cluster_identifier
            article.is_representative = article.id == representative.id

    db.commit()

    cluster_count = len(grouped_articles)
    representative_count = cluster_count
    average_cluster_size = article_count / cluster_count if cluster_count else 0.0
    logger.info(
        "Clustered %s articles into %s clusters with average cluster size %.2f",
        article_count,
        cluster_count,
        average_cluster_size,
    )
    return ClusterStats(
        article_count=article_count,
        cluster_count=cluster_count,
        representative_count=representative_count,
    ).to_dict()


def _select_representative(articles: list[SourceItem]) -> SourceItem:
    """Choose one representative article for a cluster."""

    return min(
        articles,
        key=lambda item: (-len(item.body_text.strip()), item.published_at, item.id),
    )


def _find(parent: dict[int, int], item_id: int) -> int:
    """Find the cluster root for an item."""

    current = parent[item_id]
    while current != parent[current]:
        parent[current] = parent[parent[current]]
        current = parent[current]
    parent[item_id] = current
    return current


def _union(parent: dict[int, int], left_id: int, right_id: int) -> None:
    """Merge two article sets."""

    left_root = _find(parent, left_id)
    right_root = _find(parent, right_id)
    if left_root == right_root:
        return

    if left_root < right_root:
        parent[right_root] = left_root
    else:
        parent[left_root] = right_root
