"""Pipeline trigger routes."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.schemas.pipelines import (
    FullIngestionResponse,
    NewsPipelineRunResponse,
    NewsSummarizationResponse,
    SecIngestionResponse,
    WatchlistPipelineRequest,
)
from backend.app.services.clustering.clustering_service import cluster_articles
from backend.app.pipelines.news_pipeline import run_full_ingestion, run_news_ingestion, run_sec_pipeline
from backend.app.services.ranking.ranking_service import rank_clusters
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post("/news/run", response_model=NewsPipelineRunResponse)
def run_news_pipeline(db: Session = Depends(get_db)) -> NewsPipelineRunResponse:
    """Manually trigger the news ingestion pipeline."""

    return run_news_ingestion(db)


@router.post("/sec/run", response_model=SecIngestionResponse)
def run_sec_only_pipeline(
    watchlist_id: int | None = None,
    payload: WatchlistPipelineRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> SecIngestionResponse:
    """Manually trigger SEC ingestion only."""

    resolved_watchlist_id = watchlist_id if watchlist_id is not None else (payload.watchlist_id if payload else None)
    return run_sec_pipeline(db, watchlist_id=resolved_watchlist_id)


@router.post("/full-ingest", response_model=FullIngestionResponse)
def run_full_ingest_pipeline(
    watchlist_id: int | None = None,
    payload: WatchlistPipelineRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> FullIngestionResponse:
    """Manually trigger combined news and SEC ingestion."""

    resolved_watchlist_id = watchlist_id if watchlist_id is not None else (payload.watchlist_id if payload else None)
    return run_full_ingestion(db, watchlist_id=resolved_watchlist_id)


@router.post("/news/cluster")
def run_news_clustering(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger news clustering only."""

    return cluster_articles(db)


@router.post("/news/summarize", response_model=NewsSummarizationResponse)
def run_news_summarization(db: Session = Depends(get_db)) -> NewsSummarizationResponse:
    """Manually trigger cluster summarization only."""

    return generate_cluster_summaries(db)


@router.post("/news/rank")
def run_news_ranking(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger cluster ranking only."""

    return rank_clusters(db)
