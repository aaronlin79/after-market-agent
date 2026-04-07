"""Story clustering models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, utc_now

if TYPE_CHECKING:
    from backend.app.models.source_item import SourceItem


class StoryCluster(Base):
    """A grouped set of related source items."""

    __tablename__ = "story_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    representative_title: Mapped[str] = mapped_column(Text, nullable=False)
    primary_symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    credibility_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[str] = mapped_column(String(50), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    cluster_items: Mapped[list["ClusterItem"]] = relationship(
        back_populates="cluster",
        cascade="all, delete-orphan",
    )
    summaries: Mapped[list["Summary"]] = relationship(
        back_populates="cluster",
        cascade="all, delete-orphan",
    )
    digest_entries: Mapped[list["DigestEntry"]] = relationship(back_populates="cluster")


class ClusterItem(Base):
    """Maps source items into a story cluster."""

    __tablename__ = "cluster_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id"), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_primary_source: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cluster: Mapped[StoryCluster] = relationship(back_populates="cluster_items")
    source_item: Mapped["SourceItem"] = relationship(back_populates="cluster_items")


class Summary(Base):
    """Generated summary for a story cluster."""

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), nullable=False)
    summary_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    grounded_citations_json: Mapped[list[dict[str, Any]] | dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    cluster: Mapped[StoryCluster] = relationship(back_populates="summaries")


if TYPE_CHECKING:
    from backend.app.models.digest import DigestEntry
