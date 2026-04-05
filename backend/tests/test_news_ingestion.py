"""News ingestion and pipeline tests."""

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
from backend.app.models import SourceItem
from backend.app.models.base import Base
from backend.app.pipelines.news_pipeline import run_news_ingestion
from backend.app.schemas.watchlists import WatchlistCreate, WatchlistSymbolCreate
from backend.app.services import watchlist_service
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.news_ingestion_service import ingest_news
from backend.app.services.news.normalizer import normalize_news_item


class DuplicateNewsAdapter(BaseNewsAdapter):
    """Adapter that returns duplicate news items for testing."""

    def fetch_news(
        self,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, object]]:
        published_at = end_time - timedelta(hours=1)
        return [
            {
                "external_id": "dup-1",
                "title": "Semiconductor shares rally on demand outlook",
                "body_text": "Chip names traded higher in premarket action.",
                "url": "https://mocknews.local/shared/semis-rally",
                "source_name": "MockWire",
                "published_at": published_at,
                "metadata_json": {"symbols": symbols},
            },
            {
                "external_id": "dup-2",
                "title": "Semiconductor shares rally on demand outlook",
                "body_text": "A duplicate copy from another feed.",
                "url": "https://mocknews.local/shared/semis-rally",
                "source_name": "StreetDesk",
                "published_at": published_at,
                "metadata_json": {"symbols": symbols},
            },
        ]


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Create an isolated SQLite session for ingestion tests."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Create a test client backed by an in-memory SQLite database."""

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        db = TestingSessionLocal()
        try:
            watchlist = watchlist_service.create_watchlist(
                db,
                WatchlistCreate(name="News Watchlist", description="Symbols for ingestion"),
            )
            watchlist_service.add_symbol(
                db,
                watchlist.id,
                WatchlistSymbolCreate(symbol="NVDA", company_name="NVIDIA Corporation"),
            )
            watchlist_service.add_symbol(
                db,
                watchlist.id,
                WatchlistSymbolCreate(symbol="AMD", company_name="Advanced Micro Devices, Inc."),
            )
        finally:
            db.close()

        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_normalize_news_item_uses_title_when_body_missing() -> None:
    """Normalization should clean fields and provide a body fallback."""

    normalized = normalize_news_item(
        {
            "external_id": "item-1",
            "title": "  NVDA climbs in premarket  ",
            "body_text": "   ",
            "url": " https://mocknews.local/nvda/climbs ",
            "source_name": " MockWire ",
            "published_at": datetime(2026, 4, 4, 12, 0, 0),
            "metadata_json": {"symbols": ["NVDA"]},
        }
    )

    assert normalized["title"] == "NVDA climbs in premarket"
    assert normalized["body_text"] == "NVDA climbs in premarket"
    assert normalized["source_name"] == "MockWire"
    assert normalized["published_at"].tzinfo == UTC


def test_ingestion_inserts_new_records(db_session: Session) -> None:
    """New ingestion items should be stored in SourceItem."""

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=24)

    stats = ingest_news(
        db=db_session,
        symbols=["NVDA", "AMD"],
        start_time=start_time,
        end_time=end_time,
    )

    count = db_session.execute(select(func.count(SourceItem.id))).scalar_one()
    assert stats["fetched_count"] >= 4
    assert stats["inserted_count"] > 0
    assert count == stats["inserted_count"]


def test_duplicate_items_are_not_inserted_twice(db_session: Session) -> None:
    """Duplicate content hashes should be skipped cleanly."""

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(hours=24)

    first_run = ingest_news(
        db=db_session,
        symbols=["NVDA", "AMD"],
        start_time=start_time,
        end_time=end_time,
        adapter=DuplicateNewsAdapter(),
    )
    second_run = ingest_news(
        db=db_session,
        symbols=["NVDA", "AMD"],
        start_time=start_time,
        end_time=end_time,
        adapter=DuplicateNewsAdapter(),
    )

    count = db_session.execute(select(func.count(SourceItem.id))).scalar_one()
    assert first_run == {"fetched_count": 2, "inserted_count": 1, "skipped_duplicates": 1}
    assert second_run == {"fetched_count": 2, "inserted_count": 0, "skipped_duplicates": 2}
    assert count == 1


def test_pipeline_returns_expected_counts(db_session: Session) -> None:
    """Pipeline should ingest news for watchlist symbols and return stats."""

    watchlist = watchlist_service.create_watchlist(
        db_session,
        WatchlistCreate(name="Pipeline Watchlist", description="Pipeline symbols"),
    )
    watchlist_service.add_symbol(
        db_session,
        watchlist.id,
        WatchlistSymbolCreate(symbol="MSFT", company_name="Microsoft Corporation"),
    )
    watchlist_service.add_symbol(
        db_session,
        watchlist.id,
        WatchlistSymbolCreate(symbol="AAPL", company_name="Apple Inc."),
    )

    stats = run_news_ingestion(db_session, adapter=DuplicateNewsAdapter())

    assert stats["fetched_count"] == 2
    assert stats["inserted_count"] == 1
    assert stats["skipped_duplicates"] == 1
    assert stats["cluster_count"] == 1
    assert stats["representative_count"] == 1


def test_news_pipeline_endpoint_runs(client: TestClient) -> None:
    """Manual pipeline endpoint should return ingestion stats."""

    response = client.post("/pipelines/news/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["fetched_count"] >= 1
    assert payload["inserted_count"] >= 1
    assert payload["skipped_duplicates"] >= 0
    assert payload["cluster_count"] >= 1
    assert payload["representative_count"] == payload["cluster_count"]
    assert payload["summaries_generated"] >= 1


def test_news_cluster_endpoint_runs(client: TestClient) -> None:
    """Manual clustering endpoint should return clustering stats."""

    client.post("/pipelines/news/run")

    response = client.post("/pipelines/news/cluster")

    assert response.status_code == 200
    payload = response.json()
    assert payload["article_count"] >= 1
    assert payload["cluster_count"] >= 1
    assert payload["representative_count"] == payload["cluster_count"]
