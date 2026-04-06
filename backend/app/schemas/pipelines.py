"""Pipeline response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NewsSummarizationResponse(BaseModel):
    """Response payload for manual cluster summarization runs."""

    clusters_processed: int
    summaries_generated: int
    skipped_clusters: int
    skipped_due_to_limits: int
    summarizer_used: Literal["openai", "baseline"]
    openai_count: int
    openai_calls_made: int
    baseline_count: int
    fallback_count: int


class NewsPipelineRunResponse(BaseModel):
    """Response payload for the end-to-end news pipeline run."""

    fetched_count: int
    inserted_count: int
    skipped_duplicates: int
    cluster_count: int
    representative_count: int
    summaries_generated: int
    clusters_processed: int
    openai_calls_made: int
    fallback_count: int
    skipped_due_to_limits: int
    ranked_count: int
    digest_generated: bool
    digest_id: int | None
    surfaced_item_count: int
