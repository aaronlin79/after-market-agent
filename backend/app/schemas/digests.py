"""Digest request schemas."""

from pydantic import BaseModel, Field


class DigestGenerateRequest(BaseModel):
    """Request payload for digest generation."""

    watchlist_id: int = Field(..., gt=0)


class MorningRunRequest(BaseModel):
    """Request payload for executing the full morning run."""

    watchlist_id: int = Field(..., gt=0)
