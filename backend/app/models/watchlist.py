"""Watchlist models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin, utc_now

if TYPE_CHECKING:
    from backend.app.models.digest import Digest


class Watchlist(TimestampMixin, Base):
    """A named collection of symbols to monitor."""

    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    symbols: Mapped[list["WatchlistSymbol"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
    )
    digests: Mapped[list["Digest"]] = relationship(back_populates="watchlist")


class WatchlistSymbol(Base):
    """A symbol tracked within a watchlist."""

    __tablename__ = "watchlist_symbols"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_symbols_watchlist_id_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    watchlist: Mapped[Watchlist] = relationship(back_populates="symbols")
