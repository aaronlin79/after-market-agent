"""Summary retrieval routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.services.summarization.cluster_summary_service import list_cluster_summaries

router = APIRouter(tags=["summaries"])


@router.get("/summaries")
def get_summaries(db: Session = Depends(get_db)) -> list[dict[str, int | str]]:
    """Return stored cluster summaries."""

    return list_cluster_summaries(db)
