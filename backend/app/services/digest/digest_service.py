"""Morning digest generation service."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import ClusterSummary, Digest, DigestEntry, SourceItem, StoryCluster, Watchlist, WatchlistSymbol
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run

logger = logging.getLogger(__name__)

SECTION_ORDER = [
    "Must Know",
    "Watch at Open",
    "Undercovered but Important",
    "SEC Filings Worth Checking",
    "Likely Noise",
]


def generate_morning_digest(db: Session, watchlist_id: int) -> dict[str, Any]:
    """Generate or replace the morning digest for a watchlist and run date."""

    run = start_pipeline_run(db, run_type="digest_generation", watchlist_id=watchlist_id, provider_used="local")
    try:
        watchlist = db.execute(
            select(Watchlist)
            .options(selectinload(Watchlist.symbols))
            .where(Watchlist.id == watchlist_id)
        ).scalar_one_or_none()
        if watchlist is None:
            raise ValueError(f"Watchlist {watchlist_id} was not found.")

        watchlist_symbols = {symbol.symbol.strip().upper() for symbol in watchlist.symbols if symbol.symbol.strip()}
        ranked_clusters = _load_ranked_clusters_for_watchlist(db, watchlist_symbols)
        digest_items = [_build_digest_item(db, cluster) for cluster in ranked_clusters]

        sectioned_items: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTION_ORDER}
        for item in digest_items:
            section_name = _determine_section(item)
            item["section_name"] = section_name
            sectioned_items[section_name].append(item)

        for section_name in SECTION_ORDER:
            sectioned_items[section_name].sort(
                key=lambda item: (-item["importance_score"], item["primary_symbol"], item["cluster_key"])
            )

        section_counts = {section: len(items) for section, items in sectioned_items.items() if items}
        surfaced_item_count = sum(section_counts.values())
        run_date = datetime.now(UTC).date()
        subject_line = _build_subject_line(digest_items, run_date)
        markdown = _render_markdown(run_date, sectioned_items)
        html = _render_html(run_date, sectioned_items)

        digest = _upsert_digest(
            db=db,
            watchlist_id=watchlist_id,
            run_date=run_date,
            subject_line=subject_line,
            markdown=markdown,
            html=html,
            sectioned_items=sectioned_items,
        )

        logger.info(
            "Generated digest watchlist_id=%s considered_clusters=%s surfaced_items=%s sections=%s digest_id=%s",
            watchlist_id,
            len(ranked_clusters),
            surfaced_item_count,
            section_counts,
            digest.id,
        )
        result = {
            "digest_id": digest.id,
            "watchlist_id": watchlist_id,
            "run_date": str(run_date),
            "section_counts": section_counts,
            "surfaced_item_count": surfaced_item_count,
            "subject_line": subject_line,
        }
        complete_pipeline_run(db, run, metrics_json=result, provider_used="local")
        return result
    except Exception as exc:
        fail_pipeline_run(db, run, error=exc, provider_used="local")
        logger.exception("Digest generation failed for watchlist_id=%s", watchlist_id)
        raise


def list_digests(db: Session) -> list[dict[str, Any]]:
    """List stored digests newest first."""

    digests = list(
        db.execute(
            select(Digest).order_by(Digest.run_date.desc(), Digest.generated_at.desc(), Digest.id.desc())
        ).scalars()
    )
    return [
        {
            "id": digest.id,
            "watchlist_id": digest.watchlist_id,
            "run_date": str(digest.run_date),
            "subject_line": digest.subject_line,
            "delivery_status": digest.delivery_status,
            "generated_at": digest.generated_at.isoformat(),
        }
        for digest in digests
    ]


def get_digest(db: Session, digest_id: int) -> dict[str, Any] | None:
    """Return a stored digest with entries."""

    digest = db.execute(
        select(Digest)
        .options(selectinload(Digest.entries))
        .where(Digest.id == digest_id)
    ).scalar_one_or_none()
    if digest is None:
        return None

    cluster_lookup = {
        cluster.id: cluster
        for cluster in db.execute(
            select(StoryCluster).where(StoryCluster.id.in_([entry.cluster_id for entry in digest.entries]))
        ).scalars()
    }
    summary_lookup = {
        summary.cluster_id: summary
        for summary in db.execute(
            select(ClusterSummary).where(
                ClusterSummary.cluster_id.in_(
                    [
                        cluster.cluster_key
                        for cluster in cluster_lookup.values()
                    ]
                )
            )
        ).scalars()
    }
    article_count_lookup = _article_count_lookup(db)

    entries = sorted(digest.entries, key=lambda entry: (SECTION_ORDER.index(entry.section_name), entry.rank))
    return {
        "id": digest.id,
        "watchlist_id": digest.watchlist_id,
        "run_date": str(digest.run_date),
        "subject_line": digest.subject_line,
        "delivery_status": digest.delivery_status,
        "generated_at": digest.generated_at.isoformat(),
        "sent_at": digest.sent_at.isoformat() if digest.sent_at else None,
        "digest_markdown": digest.digest_markdown,
        "digest_html": digest.digest_html,
        "entries": [
            {
                "id": entry.id,
                "section_name": entry.section_name,
                "rank": entry.rank,
                "cluster_id": entry.cluster_id,
                "cluster_key": cluster_lookup[entry.cluster_id].cluster_key if entry.cluster_id in cluster_lookup else None,
                "representative_title": (
                    cluster_lookup[entry.cluster_id].representative_title if entry.cluster_id in cluster_lookup else None
                ),
                "primary_symbol": (
                    cluster_lookup[entry.cluster_id].primary_symbol if entry.cluster_id in cluster_lookup else None
                ),
                "event_type": cluster_lookup[entry.cluster_id].event_type if entry.cluster_id in cluster_lookup else None,
                "confidence": cluster_lookup[entry.cluster_id].confidence if entry.cluster_id in cluster_lookup else None,
                "importance_score": (
                    cluster_lookup[entry.cluster_id].importance_score if entry.cluster_id in cluster_lookup else None
                ),
                "article_count": (
                    article_count_lookup.get(cluster_lookup[entry.cluster_id].cluster_key, 0)
                    if entry.cluster_id in cluster_lookup
                    else 0
                ),
                "summary_text": (
                    summary_lookup[cluster_lookup[entry.cluster_id].cluster_key].summary_text
                    if entry.cluster_id in cluster_lookup and cluster_lookup[entry.cluster_id].cluster_key in summary_lookup
                    else None
                ),
                "why_it_matters": (
                    _extract_why_it_matters(
                        summary_lookup.get(cluster_lookup[entry.cluster_id].cluster_key)
                    )
                    if entry.cluster_id in cluster_lookup
                    else None
                ),
                "unknowns": (
                    _extract_unknowns(
                        summary_lookup.get(cluster_lookup[entry.cluster_id].cluster_key)
                    )
                    if entry.cluster_id in cluster_lookup
                    else []
                ),
                "undercovered_important": entry.section_name == "Undercovered but Important",
                "rationale_json": entry.rationale_json,
            }
            for entry in entries
        ],
        "section_names": [section for section in SECTION_ORDER if any(entry.section_name == section for entry in entries)],
        "cluster_ids": [
            cluster_lookup[entry.cluster_id].cluster_key
            for entry in entries
            if entry.cluster_id in cluster_lookup
        ],
    }


def _load_ranked_clusters_for_watchlist(db: Session, watchlist_symbols: set[str]) -> list[StoryCluster]:
    clusters = list(
        db.execute(
            select(StoryCluster).order_by(
                StoryCluster.importance_score.desc(),
                StoryCluster.last_seen_at.desc(),
                StoryCluster.id.asc(),
            )
        ).scalars()
    )
    if not clusters:
        logger.info(
            "Digest candidate scan ranked_loaded=0 with_summaries=0 watchlist_matches=0 after_score_filter=0 "
            "watchlist_symbols=%s exclusions={}",
            sorted(watchlist_symbols),
        )
        return []

    cluster_keys = [cluster.cluster_key for cluster in clusters]
    summaries = {
        summary.cluster_id: summary
        for summary in db.execute(
            select(ClusterSummary).where(ClusterSummary.cluster_id.in_(cluster_keys))
        ).scalars()
    }
    source_items_by_cluster: dict[str, list[SourceItem]] = defaultdict(list)
    for source_item in db.execute(
        select(SourceItem).where(SourceItem.cluster_id.in_(cluster_keys))
    ).scalars():
        if source_item.cluster_id is not None:
            source_items_by_cluster[source_item.cluster_id].append(source_item)

    matching_clusters: list[StoryCluster] = []
    exclusion_counts: dict[str, int] = defaultdict(int)
    exclusion_examples: list[dict[str, Any]] = []
    with_summaries_count = 0
    matching_with_summaries_count = 0

    for cluster in clusters:
        primary_symbol = (cluster.primary_symbol or "").strip().upper()
        article_symbols = _extract_cluster_symbols(source_items_by_cluster.get(cluster.cluster_key, []))
        summary_present = cluster.cluster_key in summaries
        if summary_present:
            with_summaries_count += 1

        matches_watchlist = primary_symbol in watchlist_symbols or bool(article_symbols & watchlist_symbols)
        if not matches_watchlist:
            exclusion_counts["watchlist_symbol_mismatch"] += 1
            if len(exclusion_examples) < 5:
                exclusion_examples.append(
                    {
                        "cluster_key": cluster.cluster_key,
                        "primary_symbol": primary_symbol or None,
                        "article_symbols": sorted(article_symbols),
                        "summary_present": summary_present,
                        "importance_score": cluster.importance_score,
                    }
                )
            continue

        matching_clusters.append(cluster)
        if summary_present:
            matching_with_summaries_count += 1

    logger.info(
        "Digest candidate scan ranked_loaded=%s with_summaries=%s watchlist_matches=%s "
        "matching_with_summaries=%s after_score_filter=%s watchlist_symbols=%s exclusions=%s",
        len(clusters),
        with_summaries_count,
        len(matching_clusters),
        matching_with_summaries_count,
        len(matching_clusters),
        sorted(watchlist_symbols),
        dict(exclusion_counts),
    )
    if exclusion_examples:
        logger.info("Digest exclusion examples: %s", exclusion_examples)
    return matching_clusters


def _build_digest_item(db: Session, cluster: StoryCluster) -> dict[str, Any]:
    article_count = db.execute(
        select(SourceItem).where(SourceItem.cluster_id == cluster.cluster_key)
    ).scalars().all()
    summary = db.execute(
        select(ClusterSummary).where(ClusterSummary.cluster_id == cluster.cluster_key)
    ).scalar_one_or_none()

    article_total = len(article_count)
    summary_text = summary.summary_text if summary is not None else "No summary available."
    why_it_matters = _extract_why_it_matters(summary)
    undercovered_important = _is_undercovered_important(cluster, article_total)
    return {
        "cluster_id": cluster.id,
        "cluster_key": cluster.cluster_key,
        "representative_title": cluster.representative_title,
        "primary_symbol": cluster.primary_symbol,
        "importance_score": cluster.importance_score,
        "event_type": cluster.event_type,
        "confidence": cluster.confidence,
        "summary_text": summary_text,
        "why_it_matters": why_it_matters,
        "article_count": article_total,
        "undercovered_important": undercovered_important,
        "section_reason": _build_section_reason(cluster, article_total),
    }


def _determine_section(item: dict[str, Any]) -> str:
    if item["event_type"] == "sec_filing":
        return "SEC Filings Worth Checking"
    if item["undercovered_important"]:
        return "Undercovered but Important"
    if item["importance_score"] < 0.45 or item["confidence"] == "low":
        return "Likely Noise"
    if item["importance_score"] >= 0.75 and item["confidence"] in {"medium", "high"}:
        return "Must Know"
    return "Watch at Open"


def _build_section_reason(cluster: StoryCluster, article_count: int) -> str:
    if cluster.event_type == "sec_filing":
        return "Cluster classified as a SEC filing and should be reviewed directly."
    if _is_undercovered_important(cluster, article_count):
        return "High-importance story with limited source coverage that could still matter at the open."
    if cluster.importance_score >= 0.75 and cluster.confidence in {"medium", "high"}:
        return "High importance and confidence make this a top pre-market development."
    if cluster.importance_score < 0.45 or cluster.confidence == "low":
        return "Lower score or confidence suggests this is more likely to be noise."
    return "Relevant watchlist development worth monitoring at the open."


def _build_subject_line(items: list[dict[str, Any]], run_date: date) -> str:
    symbols: list[str] = []
    for item in items:
        symbol = item["primary_symbol"]
        if symbol not in symbols and symbol != "UNKNOWN":
            symbols.append(symbol)
    top_symbols = ", ".join(symbols[:3]) if symbols else "No Symbols"
    return f"Morning Brief — {len(items)} items | {top_symbols}"


def _render_markdown(run_date: date, sectioned_items: dict[str, list[dict[str, Any]]]) -> str:
    lines = [
        f"# Morning Brief — {run_date.isoformat()}",
        "",
        f"Generated at {datetime.now(UTC).isoformat()}",
        "",
    ]
    for section_name in SECTION_ORDER:
        items = sectioned_items[section_name]
        if not items:
            continue
        lines.append(f"## {section_name}")
        for item in items:
            lines.extend(
                [
                    f"### {item['primary_symbol']} — {item['representative_title']}",
                    f"- Event type: {item['event_type']}",
                    f"- Confidence: {item['confidence']}",
                    f"- Importance score: {item['importance_score']:.2f}",
                    f"- Article count: {item['article_count']}",
                    f"- Summary: {item['summary_text']}",
                    f"- Why it matters: {item['why_it_matters']}",
                    "",
                    "Why it matters:",
                    item["section_reason"],
                    "",
                ]
            )
    return "\n".join(lines).strip()


def _render_html(run_date: date, sectioned_items: dict[str, list[dict[str, Any]]]) -> str:
    parts = [
        "<html><body>",
        f"<h1>Morning Brief — {run_date.isoformat()}</h1>",
        f"<p>Generated at {datetime.now(UTC).isoformat()}</p>",
    ]
    for section_name in SECTION_ORDER:
        items = sectioned_items[section_name]
        if not items:
            continue
        parts.append(f"<h2>{section_name}</h2>")
        for item in items:
            parts.extend(
                [
                    f"<h3>{item['primary_symbol']} — {item['representative_title']}</h3>",
                    "<ul>",
                    f"<li>Event type: {item['event_type']}</li>",
                    f"<li>Confidence: {item['confidence']}</li>",
                    f"<li>Importance score: {item['importance_score']:.2f}</li>",
                    f"<li>Article count: {item['article_count']}</li>",
                    f"<li>Summary: {item['summary_text']}</li>",
                    f"<li>Why it matters: {item['why_it_matters']}</li>",
                    "</ul>",
                    f"<p><strong>Why it matters:</strong> {item['section_reason']}</p>",
                ]
            )
    parts.append("</body></html>")
    return "".join(parts)


def _upsert_digest(
    db: Session,
    watchlist_id: int,
    run_date: date,
    subject_line: str,
    markdown: str,
    html: str,
    sectioned_items: dict[str, list[dict[str, Any]]],
) -> Digest:
    """Replace the same-day digest for a watchlist to keep reruns deterministic."""

    digest = db.execute(
        select(Digest).where(Digest.watchlist_id == watchlist_id, Digest.run_date == run_date)
    ).scalar_one_or_none()

    if digest is None:
        digest = Digest(
            watchlist_id=watchlist_id,
            run_date=run_date,
            subject_line=subject_line,
            digest_markdown=markdown,
            digest_html=html,
            delivery_status="generated",
            generated_at=datetime.now(UTC),
        )
        db.add(digest)
        db.flush()
    else:
        db.execute(delete(DigestEntry).where(DigestEntry.digest_id == digest.id))
        digest.subject_line = subject_line
        digest.digest_markdown = markdown
        digest.digest_html = html
        digest.delivery_status = "generated"
        digest.generated_at = datetime.now(UTC)
        digest.sent_at = None
        db.add(digest)
        db.flush()

    entries: list[DigestEntry] = []
    for section_name in SECTION_ORDER:
        items = sectioned_items[section_name]
        for index, item in enumerate(items, start=1):
            entries.append(
                DigestEntry(
                    digest_id=digest.id,
                    cluster_id=item["cluster_id"],
                    section_name=section_name,
                    rank=index,
                    rationale_json={
                        "importance_score": item["importance_score"],
                        "confidence": item["confidence"],
                        "event_type": item["event_type"],
                        "article_count": item["article_count"],
                        "undercovered_important": item["undercovered_important"],
                        "section_reason": item["section_reason"],
                    },
                )
            )
    if entries:
        db.add_all(entries)
    db.commit()
    db.refresh(digest)
    return digest


def _extract_why_it_matters(summary: ClusterSummary | None) -> str:
    if summary is None or not summary.structured_payload_json:
        return "Why it matters is not available."
    value = summary.structured_payload_json.get("why_it_matters")
    return str(value).strip() if value is not None and str(value).strip() else "Why it matters is not available."


def _extract_unknowns(summary: ClusterSummary | None) -> list[str]:
    if summary is None or not summary.structured_payload_json:
        return []
    value = summary.structured_payload_json.get("unknowns")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _is_undercovered_important(cluster: StoryCluster, article_count: int) -> bool:
    return cluster.importance_score >= 0.7 and article_count <= 1


def _article_count_lookup(db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cluster_id in db.execute(select(SourceItem.cluster_id).where(SourceItem.cluster_id.is_not(None))).scalars():
        counts[cluster_id] = counts.get(cluster_id, 0) + 1
    return counts


def _extract_cluster_symbols(source_items: list[SourceItem]) -> set[str]:
    symbols: set[str] = set()
    for source_item in source_items:
        metadata = source_item.metadata_json or {}
        symbols.update(_extract_symbols_from_metadata(metadata))
    return symbols


def _extract_symbols_from_metadata(metadata: dict[str, Any]) -> set[str]:
    values: list[str] = []
    metadata_symbols = metadata.get("symbols")
    if isinstance(metadata_symbols, list):
        values.extend(str(value) for value in metadata_symbols)

    for key in ("symbol", "ticker"):
        value = metadata.get(key)
        if value is not None:
            values.append(str(value))

    related = metadata.get("related")
    if isinstance(related, str):
        values.extend(part.strip() for part in related.split(","))

    normalized: set[str] = set()
    for value in values:
        symbol = str(value).strip().upper()
        if symbol:
            normalized.add(symbol)
    return normalized
