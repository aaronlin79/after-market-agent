"""Digest models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, utc_now

if TYPE_CHECKING:
    from backend.app.models.story_cluster import StoryCluster
    from backend.app.models.watchlist import Watchlist


class Digest(Base):
    """A generated digest for a watchlist on a run date."""

    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    subject_line: Mapped[str] = mapped_column(String(255), nullable=False)
    digest_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    digest_html: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    watchlist: Mapped["Watchlist"] = relationship(back_populates="digests")
    entries: Mapped[list["DigestEntry"]] = relationship(
        back_populates="digest",
        cascade="all, delete-orphan",
    )


class DigestEntry(Base):
    """An ordered cluster entry inside a digest."""

    __tablename__ = "digest_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_id: Mapped[int] = mapped_column(ForeignKey("digests.id"), nullable=False)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    section_name: Mapped[str] = mapped_column(String(100), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    digest: Mapped[Digest] = relationship(back_populates="entries")
    cluster: Mapped["StoryCluster"] = relationship(back_populates="digest_entries")
