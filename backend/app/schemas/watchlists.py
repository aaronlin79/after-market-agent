"""Watchlist request and response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WatchlistCreate(BaseModel):
    """Payload for creating a watchlist."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Trim and validate watchlist names."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("Watchlist name is required.")
        return normalized


class WatchlistUpdate(BaseModel):
    """Payload for updating a watchlist."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        """Trim and validate updated watchlist names."""

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Watchlist name is required.")
        return normalized


class WatchlistSymbolCreate(BaseModel):
    """Payload for adding a symbol to a watchlist."""

    symbol: str = Field(..., min_length=1, max_length=32)
    company_name: str = Field(..., min_length=1, max_length=255)
    sector: str | None = Field(default=None, max_length=255)
    priority_weight: float = 1.0

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        """Normalize ticker symbols to uppercase."""

        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Symbol is required.")
        return normalized

    @field_validator("company_name")
    @classmethod
    def normalize_company_name(cls, value: str) -> str:
        """Trim company names."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("Company name is required.")
        return normalized

    @field_validator("sector")
    @classmethod
    def normalize_sector(cls, value: str | None) -> str | None:
        """Trim optional sector values."""

        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class WatchlistSymbolResponse(BaseModel):
    """Response model for a watchlist symbol."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int
    symbol: str
    company_name: str
    sector: str | None
    priority_weight: float
    created_at: datetime


class WatchlistListResponse(BaseModel):
    """Response model for watchlist list items."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    symbol_count: int = 0


class WatchlistResponse(BaseModel):
    """Detailed response model for a watchlist and its symbols."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    symbols: list[WatchlistSymbolResponse]
