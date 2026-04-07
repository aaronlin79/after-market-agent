"""Clustering tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models import SourceItem
from backend.app.models.base import Base
from backend.app.services.clustering.clustering_service import cluster_articles


def _create_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def _seed_article(
    db: Session,
    *,
    title: str,
    body_text: str,
    url: str,
    published_at: datetime,
) -> SourceItem:
    article = SourceItem(
        source_type="news",
        source_name="MockWire",
        external_id=url.rsplit("/", maxsplit=1)[-1],
        url=url,
        title=title,
        body_text=body_text,
        published_at=published_at,
        content_hash=url,
        metadata_json={"provider": "test"},
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def test_similar_articles_get_same_cluster_id() -> None:
    db = _create_session()
    now = datetime.now(UTC)
    try:
        first = _seed_article(
            db,
            title="NVIDIA gains after upbeat chip demand update",
            body_text="NVIDIA and peers rallied after suppliers signaled strong chip demand.",
            url="https://example.test/nvda-demand-1",
            published_at=now - timedelta(hours=1),
        )
        second = _seed_article(
            db,
            title="NVIDIA climbs on strong chip demand outlook",
            body_text="Shares rose after supply chain commentary pointed to healthy semiconductor demand.",
            url="https://example.test/nvda-demand-2",
            published_at=now - timedelta(minutes=30),
        )

        stats = cluster_articles(db, similarity_threshold=0.5)
        db.refresh(first)
        db.refresh(second)

        assert stats["cluster_count"] == 1
        assert first.cluster_id == second.cluster_id
    finally:
        db.close()


def test_dissimilar_articles_get_different_cluster_ids() -> None:
    db = _create_session()
    now = datetime.now(UTC)
    try:
        first = _seed_article(
            db,
            title="Apple unveils updated Mac lineup",
            body_text="Apple introduced new Mac hardware during its spring event.",
            url="https://example.test/apple-mac",
            published_at=now - timedelta(hours=2),
        )
        second = _seed_article(
            db,
            title="Oil futures slip on inventory build",
            body_text="Crude prices edged lower after a larger-than-expected stockpile report.",
            url="https://example.test/oil-futures",
            published_at=now - timedelta(hours=1),
        )

        stats = cluster_articles(db, similarity_threshold=0.5)
        db.refresh(first)
        db.refresh(second)

        assert stats["cluster_count"] == 2
        assert first.cluster_id != second.cluster_id
    finally:
        db.close()


def test_exactly_one_representative_per_cluster() -> None:
    db = _create_session()
    now = datetime.now(UTC)
    try:
        _seed_article(
            db,
            title="AMD rises after PC channel update",
            body_text="AMD rallied after channel checks suggested improving PC demand.",
            url="https://example.test/amd-pc-1",
            published_at=now - timedelta(hours=2),
        )
        _seed_article(
            db,
            title="AMD rises after PC channel checks improve",
            body_text="The chipmaker moved higher after checks pointed to better PC demand and improving pricing.",
            url="https://example.test/amd-pc-2",
            published_at=now - timedelta(hours=1),
        )
        _seed_article(
            db,
            title="Treasury yields ease as markets await payrolls",
            body_text="Bond yields drifted lower before the jobs report.",
            url="https://example.test/yields-payrolls",
            published_at=now - timedelta(minutes=30),
        )

        stats = cluster_articles(db, similarity_threshold=0.5)
        representatives = db.execute(
            select(func.count(SourceItem.id)).where(SourceItem.is_representative.is_(True))
        ).scalar_one()

        assert representatives == stats["cluster_count"]
        assert stats["representative_count"] == stats["cluster_count"]
    finally:
        db.close()


def test_clustering_is_deterministic() -> None:
    db = _create_session()
    now = datetime.now(UTC)
    try:
        articles = [
            _seed_article(
                db,
                title="Microsoft advances after enterprise software update",
                body_text="Microsoft gained after an enterprise software update highlighted demand stability.",
                url="https://example.test/msft-enterprise-1",
                published_at=now - timedelta(hours=2),
            ),
            _seed_article(
                db,
                title="Microsoft rises on stable enterprise demand",
                body_text="Shares moved higher after management commentary on enterprise demand.",
                url="https://example.test/msft-enterprise-2",
                published_at=now - timedelta(hours=1),
            ),
        ]

        first_run = cluster_articles(db, similarity_threshold=0.5)
        first_assignment = [(article.id, db.get(SourceItem, article.id).cluster_id) for article in articles]

        second_run = cluster_articles(db, similarity_threshold=0.5)
        second_assignment = [(article.id, db.get(SourceItem, article.id).cluster_id) for article in articles]

        assert first_run == second_run
        assert first_assignment == second_assignment
    finally:
        db.close()
