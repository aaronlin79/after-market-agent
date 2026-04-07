"""Cluster response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RankedClusterResponse(BaseModel):
    """Response model for ranked clusters."""

    cluster_id: str
    representative_title: str
    primary_symbol: str
    importance_score: float
    event_type: str | None = None
    confidence: str | None = None
    summary_text: str | None = None
    why_it_matters: str | None = None
    unknowns: list[str] = Field(default_factory=list)
    article_count: int
    undercovered_important: bool
