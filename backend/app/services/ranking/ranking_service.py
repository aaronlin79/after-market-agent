"""Deterministic cluster ranking service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import ClusterSummary, SourceItem, StoryCluster, WatchlistSymbol
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from backend.app.services.ranking.event_classifier import classify_event_type

logger = logging.getLogger(__name__)

SOURCE_CREDIBILITY = {
    "MockWire": 0.9,
    "StreetDesk": 0.7,
}

EVENT_TYPE_BOOSTS = {
    "earnings": 1.0,
    "guidance": 0.9,
    "sec_filing": 1.0,
    "m_and_a": 1.0,
    "management_change": 0.8,
    "product_launch": 0.6,
    "lawsuit_or_regulation": 0.8,
    "analyst_action": 0.5,
    "rumor": 0.2,
    "other": 0.3,
}


def rank_clusters(db: Session) -> dict[str, int]:
    """Rank recent story clusters and persist deterministic scores."""

    run = start_pipeline_run(db, run_type="ranking", provider_used="local")
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    try:
        clusters = list(
            db.execute(
                select(StoryCluster)
                .where(StoryCluster.last_seen_at >= cutoff)
                .order_by(StoryCluster.last_seen_at.desc(), StoryCluster.id.asc())
            ).scalars()
        )
        if not clusters:
            logger.info("Ranking skipped because no recent clusters were found.")
            stats = {"clusters_processed": 0, "ranked_count": 0}
            complete_pipeline_run(db, run, metrics_json=stats, provider_used="local")
            return stats

        watchlist_symbols = set(
            db.execute(select(WatchlistSymbol.symbol)).scalars().all()
        )

        ranked: list[StoryCluster] = []
        for cluster in clusters:
            articles = list(
                db.execute(
                    select(SourceItem)
                    .where(SourceItem.cluster_id == cluster.cluster_key)
                    .order_by(SourceItem.published_at.asc(), SourceItem.id.asc())
                ).scalars()
            )
            summary = db.execute(
                select(ClusterSummary).where(ClusterSummary.cluster_id == cluster.cluster_key)
            ).scalar_one_or_none()
            if not articles:
                continue

            cluster_size_score = min(len(articles) / 4, 1.0)
            relevance_score = _compute_watchlist_relevance(
                primary_symbol=cluster.primary_symbol,
                articles=articles,
                watchlist_symbols=watchlist_symbols,
            )
            credibility_score = _compute_credibility_score(articles)
            novelty_score = _compute_novelty_score(cluster.first_seen_at)
            event_type = classify_event_type(
                " ".join(
                    value
                    for value in [
                        cluster.representative_title,
                        summary.summary_text if summary is not None else "",
                    ]
                    if value
                )
            ) or "other"
            event_type_boost = EVENT_TYPE_BOOSTS.get(event_type, EVENT_TYPE_BOOSTS["other"])

            importance_score = round(
                0.30 * relevance_score
                + 0.20 * cluster_size_score
                + 0.20 * credibility_score
                + 0.20 * novelty_score
                + 0.10 * event_type_boost,
                4,
            )

            cluster.novelty_score = round(novelty_score, 4)
            cluster.credibility_score = round(credibility_score, 4)
            cluster.event_type = event_type
            cluster.importance_score = importance_score
            cluster.confidence = _assign_confidence(
                article_count=len(articles),
                credibility_score=credibility_score,
                event_type=event_type,
            )
            ranked.append(cluster)

        db.commit()

        ranked.sort(key=lambda cluster: cluster.importance_score, reverse=True)
        average_score = sum(cluster.importance_score for cluster in ranked) / len(ranked) if ranked else 0.0
        logger.info("Ranked %s clusters with average importance score %.3f", len(ranked), average_score)
        logger.info(
            "Top ranked clusters: %s",
            [
                {
                    "cluster_key": cluster.cluster_key,
                    "importance_score": cluster.importance_score,
                    "event_type": cluster.event_type,
                }
                for cluster in ranked[:5]
            ],
        )
        stats = {"clusters_processed": len(clusters), "ranked_count": len(ranked)}
        complete_pipeline_run(db, run, metrics_json=stats, provider_used="local")
        return stats
    except Exception as exc:
        fail_pipeline_run(db, run, error=exc, provider_used="local")
        logger.exception("Ranking failed.")
        raise


def list_ranked_clusters(db: Session) -> list[dict[str, int | float | str | None]]:
    """Return ranked cluster records sorted by importance."""

    clusters = list(
        db.execute(
            select(StoryCluster)
            .order_by(StoryCluster.importance_score.desc(), StoryCluster.last_seen_at.desc(), StoryCluster.id.asc())
        ).scalars()
    )
    summaries = {
        summary.cluster_id: summary
        for summary in db.execute(select(ClusterSummary)).scalars()
    }
    article_counts: dict[str, int] = {}
    for cluster_id, count in db.execute(
        select(SourceItem.cluster_id, SourceItem.id)
        .where(SourceItem.cluster_id.is_not(None))
        .order_by(SourceItem.cluster_id.asc())
    ).all():
        article_counts[cluster_id] = article_counts.get(cluster_id, 0) + 1

    return [
        {
            "cluster_id": cluster.cluster_key,
            "representative_title": cluster.representative_title,
            "primary_symbol": cluster.primary_symbol,
            "importance_score": cluster.importance_score,
            "event_type": cluster.event_type,
            "confidence": cluster.confidence,
            "summary_text": summaries[cluster.cluster_key].summary_text if cluster.cluster_key in summaries else None,
            "why_it_matters": _extract_why_it_matters(summaries.get(cluster.cluster_key)),
            "article_count": article_counts.get(cluster.cluster_key, 0),
            "undercovered_important": _is_undercovered_important(
                cluster.importance_score,
                article_counts.get(cluster.cluster_key, 0),
            ),
        }
        for cluster in clusters
    ]


def _compute_watchlist_relevance(
    primary_symbol: str,
    articles: list[SourceItem],
    watchlist_symbols: set[str],
) -> float:
    """Score watchlist relevance using cluster symbol overlap."""

    score = 0.0
    if primary_symbol in watchlist_symbols:
        score += 0.7

    mentioned_symbols: set[str] = set()
    for article in articles:
        metadata = article.metadata_json or {}
        values = metadata.get("symbols", [])
        if isinstance(values, list):
            for value in values:
                symbol = str(value).strip().upper()
                if symbol in watchlist_symbols:
                    mentioned_symbols.add(symbol)

    score += min(len(mentioned_symbols) * 0.15, 0.3)
    return min(score, 1.0)


def _compute_credibility_score(articles: list[SourceItem]) -> float:
    """Average source credibility across cluster articles."""

    if not articles:
        return 0.0
    scores = [SOURCE_CREDIBILITY.get(article.source_name, 0.5) for article in articles]
    return sum(scores) / len(scores)


def _compute_novelty_score(first_seen_at) -> float:
    """Score freshness over the last 24 hours."""

    if first_seen_at.tzinfo is None:
        first_seen_at = first_seen_at.replace(tzinfo=UTC)
    else:
        first_seen_at = first_seen_at.astimezone(UTC)

    hours_old = max((datetime.now(UTC) - first_seen_at).total_seconds() / 3600, 0.0)
    return max(0.2, 1.0 - min(hours_old / 24, 0.8))


def _assign_confidence(article_count: int, credibility_score: float, event_type: str) -> str:
    """Assign a deterministic confidence label."""

    if article_count >= 2 and credibility_score >= 0.7:
        return "high"
    if credibility_score >= 0.6 or article_count >= 2 or event_type in {"earnings", "guidance", "sec_filing", "m_and_a"}:
        return "medium"
    return "low"


def _extract_why_it_matters(summary: ClusterSummary | None) -> str | None:
    if summary is None or not summary.structured_payload_json:
        return None
    value = summary.structured_payload_json.get("why_it_matters")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _is_undercovered_important(importance_score: float, article_count: int) -> bool:
    return importance_score >= 0.7 and article_count <= 1
