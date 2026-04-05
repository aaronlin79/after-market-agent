"""Pipeline trigger routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.services.clustering.clustering_service import cluster_articles
from backend.app.pipelines.news_pipeline import run_news_ingestion

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.post("/news/run")
def run_news_pipeline(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger the news ingestion pipeline."""

    return run_news_ingestion(db)


@router.post("/news/cluster")
def run_news_clustering(db: Session = Depends(get_db)) -> dict[str, int]:
    """Manually trigger news clustering only."""

    return cluster_articles(db)
