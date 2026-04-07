"""Pipeline response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class WatchlistPipelineRequest(BaseModel):
    """Optional watchlist selection for manual pipeline runs."""

    watchlist_id: int | None = None


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
    provider_used: str


class SecIngestionResponse(BaseModel):
    """Response payload for SEC-only ingestion."""

    watchlist_id: int | None
    provider_used: Literal["sec"]
    mapped_symbol_count: int
    fetched_count: int
    inserted_count: int
    skipped_duplicates: int


class FullIngestionResponse(BaseModel):
    """Response payload for combined news and SEC ingestion."""

    watchlist_id: int | None
    provider_used: str
    news_fetched_count: int
    news_inserted_count: int
    filing_fetched_count: int
    filing_inserted_count: int
    skipped_duplicates: int
    news_error: str | None
    sec_error: str | None
