"""Digest generation tests."""

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
from backend.app.models import ClusterSummary, Digest, DigestEntry, StoryCluster, Watchlist, WatchlistSymbol
from backend.app.models.base import Base
from backend.app.services.digest.digest_service import generate_morning_digest


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


def _seed_watchlist(db: Session) -> Watchlist:
    watchlist = Watchlist(name="Digest Watchlist", description="digest")
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    db.add_all(
        [
            WatchlistSymbol(watchlist_id=watchlist.id, symbol="NVDA", company_name="NVIDIA Corporation"),
            WatchlistSymbol(watchlist_id=watchlist.id, symbol="AMD", company_name="Advanced Micro Devices, Inc."),
            WatchlistSymbol(watchlist_id=watchlist.id, symbol="MSFT", company_name="Microsoft Corporation"),
        ]
    )
    db.commit()
    return watchlist


def _seed_ranked_cluster(
    db: Session,
    *,
    cluster_key: str,
    primary_symbol: str,
    title: str,
    importance_score: float,
    confidence: str,
    event_type: str,
    summary_text: str,
) -> StoryCluster:
    now = datetime.now(UTC)
    cluster = StoryCluster(
        cluster_key=cluster_key,
        representative_title=title,
        primary_symbol=primary_symbol,
        event_type=event_type,
        importance_score=importance_score,
        novelty_score=0.8,
        credibility_score=0.8,
        confidence=confidence,
        first_seen_at=now - timedelta(hours=2),
        last_seen_at=now - timedelta(hours=1),
    )
    db.add(cluster)
    db.commit()
    db.refresh(cluster)
    db.add(ClusterSummary(cluster_id=cluster_key, summary_text=summary_text))
    db.commit()
    return cluster


def test_digest_is_generated_and_persisted(db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-1",
        primary_symbol="NVDA",
        title="NVDA raises guidance after earnings",
        importance_score=0.92,
        confidence="high",
        event_type="earnings",
        summary_text="NVIDIA raised guidance after reporting earnings.",
    )

    result = generate_morning_digest(db_session, watchlist.id)
    digest = db_session.execute(select(Digest)).scalar_one()
    entry_count = db_session.execute(select(func.count(DigestEntry.id))).scalar_one()

    assert result["digest_id"] == digest.id
    assert digest.watchlist_id == watchlist.id
    assert "Morning Brief" in digest.subject_line
    assert digest.digest_markdown
    assert digest.digest_html
    assert entry_count == 1


def test_digest_entries_sorted_by_priority_within_sections(db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    low = _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-low",
        primary_symbol="AMD",
        title="AMD product update",
        importance_score=0.76,
        confidence="high",
        event_type="product_launch",
        summary_text="AMD announced a product update.",
    )
    high = _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-high",
        primary_symbol="NVDA",
        title="NVDA raises guidance after earnings",
        importance_score=0.93,
        confidence="high",
        event_type="earnings",
        summary_text="NVIDIA raised guidance after earnings.",
    )

    result = generate_morning_digest(db_session, watchlist.id)
    digest = db_session.get(Digest, result["digest_id"])
    entries = list(
        db_session.execute(
            select(DigestEntry).where(DigestEntry.digest_id == digest.id, DigestEntry.section_name == "Must Know").order_by(DigestEntry.rank.asc())
        ).scalars()
    )

    assert [entry.cluster_id for entry in entries] == [high.id, low.id]


def test_sec_filing_clusters_are_placed_in_sec_section(db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    filing = _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-sec",
        primary_symbol="MSFT",
        title="MSFT files 8-K after board update",
        importance_score=0.61,
        confidence="medium",
        event_type="sec_filing",
        summary_text="Microsoft filed an 8-K after a board update.",
    )

    result = generate_morning_digest(db_session, watchlist.id)
    digest = db_session.get(Digest, result["digest_id"])
    entry = db_session.execute(
        select(DigestEntry).where(DigestEntry.digest_id == digest.id, DigestEntry.cluster_id == filing.id)
    ).scalar_one()

    assert entry.section_name == "SEC Filings Worth Checking"


def test_low_confidence_clusters_can_land_in_likely_noise(db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    noise = _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-noise",
        primary_symbol="AMD",
        title="AMD rumor circulates in early trading",
        importance_score=0.31,
        confidence="low",
        event_type="rumor",
        summary_text="A low-confidence rumor circulated around AMD.",
    )

    result = generate_morning_digest(db_session, watchlist.id)
    digest = db_session.get(Digest, result["digest_id"])
    entry = db_session.execute(
        select(DigestEntry).where(DigestEntry.digest_id == digest.id, DigestEntry.cluster_id == noise.id)
    ).scalar_one()

    assert entry.section_name == "Likely Noise"


def test_rerun_replaces_same_day_digest(db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-1",
        primary_symbol="NVDA",
        title="NVDA raises guidance after earnings",
        importance_score=0.92,
        confidence="high",
        event_type="earnings",
        summary_text="NVIDIA raised guidance after earnings.",
    )

    first = generate_morning_digest(db_session, watchlist.id)
    _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-2",
        primary_symbol="AMD",
        title="AMD launches new AI chip",
        importance_score=0.81,
        confidence="medium",
        event_type="product_launch",
        summary_text="AMD launched a new AI chip.",
    )
    second = generate_morning_digest(db_session, watchlist.id)

    digest_count = db_session.execute(select(func.count(Digest.id))).scalar_one()
    entry_count = db_session.execute(select(func.count(DigestEntry.id))).scalar_one()

    assert first["digest_id"] == second["digest_id"]
    assert digest_count == 1
    assert entry_count == 2


def test_subject_line_is_deterministic(db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-a",
        primary_symbol="NVDA",
        title="NVDA raises guidance after earnings",
        importance_score=0.92,
        confidence="high",
        event_type="earnings",
        summary_text="NVIDIA raised guidance after earnings.",
    )
    _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-b",
        primary_symbol="AMD",
        title="AMD launches new AI chip",
        importance_score=0.81,
        confidence="medium",
        event_type="product_launch",
        summary_text="AMD launched a new AI chip.",
    )

    first = generate_morning_digest(db_session, watchlist.id)
    second = generate_morning_digest(db_session, watchlist.id)

    assert first["subject_line"] == second["subject_line"]
    assert first["subject_line"] == "Morning Brief — 2 items | NVDA, AMD"


def test_digest_endpoints_work(client: TestClient, db_session: Session) -> None:
    watchlist = _seed_watchlist(db_session)
    _seed_ranked_cluster(
        db_session,
        cluster_key="cluster-api",
        primary_symbol="NVDA",
        title="NVDA raises guidance after earnings",
        importance_score=0.92,
        confidence="high",
        event_type="earnings",
        summary_text="NVIDIA raised guidance after earnings.",
    )

    generate_response = client.post("/digests/generate", json={"watchlist_id": watchlist.id})
    payload = generate_response.json()
    list_response = client.get("/digests")
    detail_response = client.get(f"/digests/{payload['digest_id']}")

    assert generate_response.status_code == 200
    assert payload["surfaced_item_count"] == 1
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["entries"][0]["section_name"] == "Must Know"
