"""Cluster retrieval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.services.ranking.ranking_service import list_ranked_clusters

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("/ranked")
def get_ranked_clusters(db: Session = Depends(get_db)) -> list[dict[str, int | float | str | None]]:
    """Return ranked clusters in descending importance order."""

    return list_ranked_clusters(db)
