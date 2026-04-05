"""Cluster summarization tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models import ClusterSummary, SourceItem
from backend.app.models.base import Base
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries
from backend.app.services.summarization.summarization_service import summarize_cluster


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Create an isolated SQLite session for summarization tests."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create a test client using the session fixture database."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_clustered_articles(db: Session) -> list[SourceItem]:
    now = datetime.now(UTC)
    articles = [
        SourceItem(
            source_type="news",
            source_name="MockWire",
            external_id="article-1",
            url="https://example.test/cluster-1-a",
            title="NVIDIA gains after upbeat chip demand update",
            body_text="NVIDIA rallied after suppliers signaled strong chip demand. Traders focused on data center strength.",
            published_at=now - timedelta(hours=2),
            content_hash="cluster-1-a",
            cluster_id="cluster-1",
            is_representative=True,
            metadata_json={},
        ),
        SourceItem(
            source_type="news",
            source_name="StreetDesk",
            external_id="article-2",
            url="https://example.test/cluster-1-b",
            title="NVIDIA climbs on strong semiconductor demand outlook",
            body_text="Shares rose after supply chain commentary pointed to healthy semiconductor demand.",
            published_at=now - timedelta(hours=1),
            content_hash="cluster-1-b",
            cluster_id="cluster-1",
            is_representative=False,
            metadata_json={},
        ),
    ]
    db.add_all(articles)
    db.commit()
    return articles


def test_summaries_created_for_clusters(db_session: Session) -> None:
    """Stored summaries should be created for clustered articles."""

    _seed_clustered_articles(db_session)

    stats = generate_cluster_summaries(db_session)
    summary = db_session.execute(select(ClusterSummary)).scalar_one()

    assert stats["clusters_processed"] == 1
    assert stats["summaries_generated"] == 1
    assert summary.cluster_id == "cluster-1"
    assert "NVIDIA" in summary.summary_text


def test_no_duplicate_summaries(db_session: Session) -> None:
    """Running summary generation twice should be idempotent."""

    _seed_clustered_articles(db_session)

    first_run = generate_cluster_summaries(db_session)
    second_run = generate_cluster_summaries(db_session)
    count = db_session.execute(select(func.count(ClusterSummary.id))).scalar_one()

    assert first_run["summaries_generated"] == 1
    assert second_run["summaries_generated"] == 0
    assert second_run["skipped_clusters"] == 1
    assert count == 1


def test_empty_clusters_handled_gracefully(db_session: Session) -> None:
    """No clusters should produce no summaries."""

    stats = generate_cluster_summaries(db_session)

    assert stats == {"clusters_processed": 0, "summaries_generated": 0, "skipped_clusters": 0}


def test_summarization_is_deterministic(db_session: Session) -> None:
    """The baseline summary output should be stable for the same articles."""

    articles = _seed_clustered_articles(db_session)

    first_summary = summarize_cluster(articles)
    second_summary = summarize_cluster(list(reversed(articles)))

    assert first_summary == second_summary


def test_summary_endpoints_work(client: TestClient, db_session: Session) -> None:
    """Manual summarization and retrieval endpoints should work."""

    _seed_clustered_articles(db_session)

    summarize_response = client.post("/pipelines/news/summarize")
    summaries_response = client.get("/summaries")

    assert summarize_response.status_code == 200
    assert summarize_response.json()["summaries_generated"] == 1
    assert summaries_response.status_code == 200
    payload = summaries_response.json()
    assert len(payload) == 1
    assert payload[0]["cluster_id"] == "cluster-1"
    assert payload[0]["article_count"] == 2
