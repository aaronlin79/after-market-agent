"""Pipeline trigger routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.services.clustering.clustering_service import cluster_articles
from backend.app.pipelines.news_pipeline import run_news_ingestion
from backend.app.services.ranking.ranking_service import rank_clusters
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post("/news/run")
def run_news_pipeline(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Manually trigger the news ingestion pipeline."""

    return run_news_ingestion(db)


@router.post("/news/cluster")
def run_news_clustering(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger news clustering only."""

    return cluster_articles(db)


@router.post("/news/summarize")
def run_news_summarization(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger cluster summarization only."""

    return generate_cluster_summaries(db)


@router.post("/news/rank")
def run_news_ranking(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger cluster ranking only."""

    return rank_clusters(db)
