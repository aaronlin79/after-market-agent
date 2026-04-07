"""Cluster retrieval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.schemas.clusters import RankedClusterResponse
from backend.app.services.ranking.ranking_service import list_ranked_clusters

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("/ranked", response_model=list[RankedClusterResponse])
def get_ranked_clusters(db: Session = Depends(get_db)) -> list[RankedClusterResponse]:
    """Return ranked clusters in descending importance order."""

    return [RankedClusterResponse.model_validate(item) for item in list_ranked_clusters(db)]
