"""Cluster summary model."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class ClusterSummary(TimestampMixin, Base):
    """Stored summary for a clustered news story."""

    __tablename__ = "cluster_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
