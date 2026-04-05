"""Ranking tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models import ClusterSummary, SourceItem, StoryCluster, Watchlist, WatchlistSymbol
from backend.app.models.base import Base
from backend.app.services.ranking.event_classifier import classify_event_type
from backend.app.services.ranking.ranking_service import list_ranked_clusters, rank_clusters


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
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
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _seed_watchlist(db: Session) -> None:
    watchlist = Watchlist(name="Rank List", description="ranking")
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    db.add_all(
        [
            WatchlistSymbol(watchlist_id=watchlist.id, symbol="NVDA", company_name="NVIDIA Corporation"),
            WatchlistSymbol(watchlist_id=watchlist.id, symbol="AMD", company_name="Advanced Micro Devices, Inc."),
        ]
    )
    db.commit()


def _seed_cluster(
    db: Session,
    *,
    cluster_key: str,
    primary_symbol: str,
    title: str,
    body_texts: list[str],
    source_names: list[str],
    published_at: datetime,
    summary_text: str | None = None,
) -> None:
    cluster = StoryCluster(
        cluster_key=cluster_key,
        representative_title=title,
        primary_symbol=primary_symbol,
        event_type="other",
        importance_score=0.0,
        novelty_score=0.0,
        credibility_score=0.0,
        confidence="low",
        first_seen_at=published_at,
        last_seen_at=published_at + timedelta(minutes=len(body_texts)),
    )
    db.add(cluster)
    db.commit()
    for index, (body_text, source_name) in enumerate(zip(body_texts, source_names, strict=True), start=1):
        db.add(
            SourceItem(
                source_type="news",
                source_name=source_name,
                external_id=f"{cluster_key}-{index}",
                url=f"https://example.test/{cluster_key}/{index}",
                title=title,
                body_text=body_text,
                published_at=published_at + timedelta(minutes=index),
                content_hash=f"{cluster_key}-{index}",
                cluster_id=cluster_key,
                is_representative=index == 1,
                metadata_json={"symbols": [primary_symbol]},
            )
        )
    if summary_text is not None:
        db.add(ClusterSummary(cluster_id=cluster_key, summary_text=summary_text))
    db.commit()


def test_clusters_are_ranked_in_descending_order(db_session: Session) -> None:
    _seed_watchlist(db_session)
    now = datetime.now(UTC)
    _seed_cluster(
        db_session,
        cluster_key="cluster-1",
        primary_symbol="NVDA",
        title="NVDA earnings outlook improves",
        body_texts=[
            "NVIDIA rallied after strong earnings guidance.",
            "A second source highlighted strong earnings guidance and demand.",
        ],
        source_names=["MockWire", "StreetDesk"],
        published_at=now - timedelta(hours=1),
        summary_text="NVIDIA guidance improved.",
    )
    _seed_cluster(
        db_session,
        cluster_key="cluster-2",
        primary_symbol="AMD",
        title="AMD commentary remains mixed",
        body_texts=["AMD commentary was mixed during trading."],
        source_names=["StreetDesk"],
        published_at=now - timedelta(hours=8),
        summary_text="AMD commentary remained mixed.",
    )

    rank_clusters(db_session)
    ranked = list_ranked_clusters(db_session)

    assert ranked[0]["importance_score"] >= ranked[1]["importance_score"]


def test_high_signal_keyword_clusters_outrank_generic_commentary(db_session: Session) -> None:
    _seed_watchlist(db_session)
    now = datetime.now(UTC)
    _seed_cluster(
        db_session,
        cluster_key="cluster-earnings",
        primary_symbol="NVDA",
        title="NVDA earnings guidance raised after results",
        body_texts=["NVIDIA raised guidance after reporting quarterly earnings."],
        source_names=["MockWire"],
        published_at=now - timedelta(hours=2),
        summary_text="NVIDIA raised guidance after earnings.",
    )
    _seed_cluster(
        db_session,
        cluster_key="cluster-generic",
        primary_symbol="NVDA",
        title="NVDA shares active in premarket commentary",
        body_texts=["Premarket commentary remained active."],
        source_names=["MockWire"],
        published_at=now - timedelta(hours=2),
        summary_text="Premarket commentary remained active.",
    )

    rank_clusters(db_session)
    ranked = {row["cluster_id"]: row for row in list_ranked_clusters(db_session)}

    assert ranked["cluster-earnings"]["importance_score"] > ranked["cluster-generic"]["importance_score"]
    assert ranked["cluster-earnings"]["event_type"] == "earnings"


def test_larger_clusters_score_higher_when_other_factors_similar(db_session: Session) -> None:
    _seed_watchlist(db_session)
    now = datetime.now(UTC)
    _seed_cluster(
        db_session,
        cluster_key="cluster-large",
        primary_symbol="NVDA",
        title="NVDA product update drives attention",
        body_texts=[
            "NVIDIA launched a new product.",
            "Another article covered the same product launch.",
            "A third article covered the same product launch.",
        ],
        source_names=["MockWire", "StreetDesk", "MockWire"],
        published_at=now - timedelta(hours=3),
        summary_text="NVIDIA launched a new product.",
    )
    _seed_cluster(
        db_session,
        cluster_key="cluster-small",
        primary_symbol="NVDA",
        title="NVDA product update drives attention",
        body_texts=["NVIDIA launched a new product."],
        source_names=["MockWire"],
        published_at=now - timedelta(hours=3),
        summary_text="NVIDIA launched a new product.",
    )

    rank_clusters(db_session)
    ranked = {row["cluster_id"]: row for row in list_ranked_clusters(db_session)}

    assert ranked["cluster-large"]["importance_score"] > ranked["cluster-small"]["importance_score"]


def test_confidence_labels_are_assigned_deterministically(db_session: Session) -> None:
    _seed_watchlist(db_session)
    now = datetime.now(UTC)
    _seed_cluster(
        db_session,
        cluster_key="cluster-high-confidence",
        primary_symbol="NVDA",
        title="NVDA earnings beat expectations",
        body_texts=["NVIDIA beat earnings expectations.", "A second report confirmed the earnings beat."],
        source_names=["MockWire", "StreetDesk"],
        published_at=now - timedelta(hours=1),
        summary_text="NVIDIA beat earnings expectations.",
    )

    first = rank_clusters(db_session)
    second = rank_clusters(db_session)
    ranked = {row["cluster_id"]: row for row in list_ranked_clusters(db_session)}

    assert first == second
    assert ranked["cluster-high-confidence"]["confidence"] == "high"


def test_event_classifier_returns_expected_labels() -> None:
    assert classify_event_type("Company raises guidance after quarterly earnings") == "earnings"
    assert classify_event_type("Company files 8-K with the SEC") == "sec_filing"
    assert classify_event_type("CEO resigns and board appoints interim leader") == "management_change"
    assert classify_event_type("Analyst upgrades shares and lifts price target") == "analyst_action"


def test_rank_endpoints_work(client: TestClient, db_session: Session) -> None:
    _seed_watchlist(db_session)
    now = datetime.now(UTC)
    _seed_cluster(
        db_session,
        cluster_key="cluster-api",
        primary_symbol="NVDA",
        title="NVDA raises guidance after earnings",
        body_texts=["NVIDIA raised guidance after earnings."],
        source_names=["MockWire"],
        published_at=now - timedelta(hours=1),
        summary_text="NVIDIA raised guidance after earnings.",
    )

    rank_response = client.post("/pipelines/news/rank")
    ranked_response = client.get("/clusters/ranked")

    assert rank_response.status_code == 200
    assert rank_response.json()["ranked_count"] == 1
    assert ranked_response.status_code == 200
    payload = ranked_response.json()
    assert len(payload) == 1
    assert payload[0]["cluster_id"] == "cluster-api"
    assert payload[0]["summary_text"] == "NVIDIA raised guidance after earnings."
