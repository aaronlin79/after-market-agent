"""Cluster summary generation service."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings, get_settings
from backend.app.models import ClusterSummary, SourceItem
from backend.app.services.openai.openai_client import OpenAIResponsesClient
from backend.app.services.observability.pipeline_tracker import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from backend.app.services.summarization.openai_cluster_summarizer import summarize_cluster_with_openai
from backend.app.services.summarization.summarization_service import build_baseline_cluster_summary_result

logger = logging.getLogger(__name__)


def generate_cluster_summaries(
    db: Session,
    *,
    settings: Settings | None = None,
    openai_client: OpenAIResponsesClient | None = None,
) -> dict[str, Any]:
    """Generate summaries for clustered articles, preferring OpenAI when configured."""

    resolved_settings = settings or get_settings()
    use_openai = bool(resolved_settings.openai_api_key)
    run = start_pipeline_run(
        db,
        run_type="summarization",
        provider_used=resolved_settings.openai_model_summary if use_openai else "baseline",
        metrics_json={"has_openai_api_key": use_openai},
    )
    max_clusters_per_run = max(int(resolved_settings.openai_max_clusters_per_run), 0)
    max_calls_per_run = max(int(resolved_settings.openai_max_calls_per_run), 0)
    cluster_ids = list(
        db.execute(
            select(SourceItem.cluster_id)
            .where(SourceItem.cluster_id.is_not(None))
            .group_by(SourceItem.cluster_id)
            .order_by(SourceItem.cluster_id.asc())
        ).scalars()
    )

    logger.info(
        "Starting cluster summarization run cluster_count=%s has_openai_api_key=%s model=%s max_clusters_per_run=%s max_calls_per_run=%s",
        len(cluster_ids),
        bool(resolved_settings.openai_api_key),
        resolved_settings.openai_model_summary,
        max_clusters_per_run,
        max_calls_per_run,
    )

    if not cluster_ids:
        logger.info("Cluster summarization skipped because no clusters were found.")
        result = {
            "clusters_processed": 0,
            "summaries_generated": 0,
            "skipped_clusters": 0,
            "skipped_due_to_limits": 0,
            "summarizer_used": "openai" if use_openai else "baseline",
            "openai_count": 0,
            "openai_calls_made": 0,
            "baseline_count": 0,
            "fallback_count": 0,
        }
        complete_pipeline_run(
            db,
            run,
            metrics_json=result,
            provider_used="openai" if use_openai else "baseline",
        )
        return result

    existing_summaries = {
        summary.cluster_id: summary
        for summary in db.execute(select(ClusterSummary).where(ClusterSummary.cluster_id.in_(cluster_ids))).scalars()
    }

    summaries_generated = 0
    skipped_clusters = 0
    skipped_due_to_limits = 0
    clusters_processed = 0
    openai_count = 0
    openai_calls_made = 0
    baseline_count = 0
    fallback_count = 0

    for cluster_id in cluster_ids:
        if clusters_processed >= max_clusters_per_run:
            remaining_clusters = len(cluster_ids) - clusters_processed
            skipped_due_to_limits += remaining_clusters
            logger.warning(
                "Cluster summarization limit reached: processed=%s max_clusters_per_run=%s skipped_due_to_limits=%s",
                clusters_processed,
                max_clusters_per_run,
                skipped_due_to_limits,
            )
            break

        existing_summary = existing_summaries.get(cluster_id)
        if _should_skip_summary(existing_summary, use_openai, resolved_settings):
            logger.info(
                "Skipping cluster_id=%s because an up-to-date summary already exists model_name=%s",
                cluster_id,
                existing_summary.model_name if existing_summary is not None else None,
            )
            skipped_clusters += 1
            clusters_processed += 1
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
            clusters_processed += 1
            continue

        summarizer_used = "openai" if use_openai else "baseline"
        fallback_reason: str | None = None
        attempted_openai = False
        try:
            if use_openai and openai_calls_made < max_calls_per_run:
                attempted_openai = True
                logger.info(
                    "Entering OpenAI summarizer branch for cluster_id=%s model=%s openai_calls_made=%s",
                    cluster_id,
                    resolved_settings.openai_model_summary,
                    openai_calls_made,
                )
                summary_result = summarize_cluster_with_openai(
                    articles,
                    settings=resolved_settings,
                    client=openai_client,
                )
                openai_calls_made += 1
                openai_count += 1
            else:
                if use_openai and openai_calls_made >= max_calls_per_run:
                    fallback_reason = "openai_call_limit_reached"
                    logger.warning(
                        "OpenAI call limit reached: cluster_id=%s openai_calls_made=%s max_calls_per_run=%s; using baseline summarizer.",
                        cluster_id,
                        openai_calls_made,
                        max_calls_per_run,
                    )
                elif not use_openai:
                    fallback_reason = "openai_not_configured"
                    logger.warning(
                        "OpenAI summarization disabled for cluster_id=%s because OPENAI_API_KEY is missing; using baseline summarizer.",
                        cluster_id,
                    )
                summary_result = build_baseline_cluster_summary_result(articles)
                baseline_count += 1
                summarizer_used = "baseline"
        except Exception as exc:
            if not use_openai:
                logger.exception("Baseline summarization failed for cluster_id=%s", cluster_id)
                skipped_clusters += 1
                clusters_processed += 1
                continue
            if attempted_openai:
                openai_calls_made += 1
            fallback_reason = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "OpenAI summarization failed for cluster_id=%s model=%s error_type=%s error=%s; falling back to baseline summarizer.",
                cluster_id,
                resolved_settings.openai_model_summary,
                type(exc).__name__,
                exc,
            )
            summary_result = build_baseline_cluster_summary_result(articles)
            baseline_count += 1
            fallback_count += 1
            summarizer_used = "baseline"
            logger.info(
                "Baseline fallback used for cluster_id=%s reason=%s",
                cluster_id,
                fallback_reason,
            )

        if existing_summary is None:
            existing_summary = ClusterSummary(cluster_id=cluster_id, summary_text=summary_result.rendered_summary_text)
            db.add(existing_summary)
        existing_summary.summary_text = summary_result.rendered_summary_text
        existing_summary.model_name = summary_result.model_name
        existing_summary.prompt_version = summary_result.prompt_version
        existing_summary.structured_payload_json = {
            "headline": summary_result.headline,
            "summary_bullets": summary_result.summary_bullets,
            "why_it_matters": summary_result.why_it_matters,
            "confidence": summary_result.confidence,
            "unknowns": summary_result.unknowns,
            "cited_source_indices": summary_result.cited_source_indices,
            "summarizer_used": summarizer_used,
            "fallback_reason": fallback_reason,
        }
        summaries_generated += 1
        logger.info(
            "Cluster summary generated cluster_id=%s summarizer=%s model=%s prompt_version=%s fallback_reason=%s",
            cluster_id,
            summarizer_used,
            summary_result.model_name,
            summary_result.prompt_version,
            fallback_reason,
        )
        clusters_processed += 1

    run_summarizer_used = _resolve_run_summarizer_used(use_openai, openai_count, baseline_count)
    db.commit()
    logger.info(
        "Cluster summarization complete: processed=%s generated=%s skipped=%s skipped_due_to_limits=%s run_summarizer_used=%s openai=%s openai_calls_made=%s baseline=%s fallback=%s",
        clusters_processed,
        summaries_generated,
        skipped_clusters,
        skipped_due_to_limits,
        run_summarizer_used,
        openai_count,
        openai_calls_made,
        baseline_count,
        fallback_count,
    )
    result = {
        "clusters_processed": clusters_processed,
        "summaries_generated": summaries_generated,
        "skipped_clusters": skipped_clusters,
        "skipped_due_to_limits": skipped_due_to_limits,
        "summarizer_used": run_summarizer_used,
        "openai_count": openai_count,
        "openai_calls_made": openai_calls_made,
        "baseline_count": baseline_count,
        "fallback_count": fallback_count,
    }
    final_status = "partial_success" if fallback_count > 0 or skipped_due_to_limits > 0 else "success"
    complete_pipeline_run(
        db,
        run,
        status=final_status,
        metrics_json=result,
        provider_used=run_summarizer_used,
    )
    return result


def list_cluster_summaries(db: Session) -> list[dict[str, int | str]]:
    """Return stored cluster summaries with article counts."""

    rows = db.execute(
        select(
            ClusterSummary.cluster_id,
            ClusterSummary.summary_text,
            ClusterSummary.model_name,
            ClusterSummary.prompt_version,
            func.count(SourceItem.id).label("article_count"),
        )
        .outerjoin(SourceItem, SourceItem.cluster_id == ClusterSummary.cluster_id)
        .group_by(
            ClusterSummary.id,
            ClusterSummary.cluster_id,
            ClusterSummary.summary_text,
            ClusterSummary.model_name,
            ClusterSummary.prompt_version,
        )
        .order_by(ClusterSummary.cluster_id.asc())
    ).all()

    return [
        {
            "cluster_id": cluster_id,
            "summary_text": summary_text,
            "model_name": model_name,
            "prompt_version": prompt_version,
            "article_count": article_count,
        }
        for cluster_id, summary_text, model_name, prompt_version, article_count in rows
    ]


def _should_skip_summary(
    existing_summary: ClusterSummary | None,
    use_openai: bool,
    settings: Settings,
) -> bool:
    if existing_summary is None:
        return False
    if not use_openai:
        return True
    return (
        existing_summary.model_name == settings.openai_model_summary
        and existing_summary.structured_payload_json is not None
    )


def _resolve_run_summarizer_used(use_openai: bool, openai_count: int, baseline_count: int) -> str:
    """Return the aggregate summarizer label for a run."""

    if openai_count > 0:
        return "openai"
    if baseline_count > 0:
        return "baseline"
    return "openai" if use_openai else "baseline"
