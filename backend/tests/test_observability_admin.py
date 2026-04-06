"""Observability, admin, and eval tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models import ClusterSummary, Digest, DigestEntry, PipelineRun, SourceItem, StoryCluster
from backend.app.models.base import Base
from backend.app.services.news.adapters.base import BaseNewsAdapter
from backend.app.services.news.news_ingestion_service import ingest_news
from backend.evals.evaluation_runner import run_local_evaluations


class SimpleNewsAdapter(BaseNewsAdapter):
    def fetch_news(self, symbols: list[str], start_time: datetime, end_time: datetime):
        return [
            {
                "external_id": "simple-1",
                "title": f"{symbols[0]} rises after update",
                "body_text": "Investors reacted to a positive company update.",
                "url": "https://example.test/simple-1",
                "source_name": "MockWire",
                "published_at": end_time - timedelta(minutes=10),
                "metadata_json": {"symbols": [symbols[0]]},
            }
        ]


class FailingNewsAdapter(BaseNewsAdapter):
    def fetch_news(self, symbols: list[str], start_time: datetime, end_time: datetime):
        raise RuntimeError("forced adapter failure")


def _make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_pipeline_run_records_are_created_and_updated() -> None:
    db = _make_session()
    try:
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=1)
        stats = ingest_news(db, ["NVDA"], start_time, end_time, adapter=SimpleNewsAdapter())

        run = db.execute(select(PipelineRun).where(PipelineRun.run_type == "news_ingestion")).scalar_one()
        assert stats["inserted_count"] == 1
        assert run.status == "success"
        assert run.completed_at is not None
        assert run.metrics_json is not None
        assert run.metrics_json["inserted_count"] == 1
    finally:
        db.close()


def test_failed_pipeline_runs_persist_error_message() -> None:
    db = _make_session()
    try:
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(hours=1)
        try:
            ingest_news(db, ["NVDA"], start_time, end_time, adapter=FailingNewsAdapter())
        except RuntimeError:
            pass

        run = db.execute(select(PipelineRun).where(PipelineRun.run_type == "news_ingestion")).scalar_one()
        assert run.status == "failed"
        assert run.error_message is not None
        assert "forced adapter failure" in run.error_message
    finally:
        db.close()


def test_admin_endpoints_return_expected_structures() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    seed_db = SessionLocal()
    cluster = StoryCluster(
        cluster_key="cluster-admin-1",
        representative_title="NVIDIA raises guidance",
        primary_symbol="NVDA",
        event_type="guidance",
        importance_score=0.91,
        novelty_score=0.88,
        credibility_score=0.85,
        confidence="high",
        first_seen_at=datetime.now(UTC) - timedelta(hours=2),
        last_seen_at=datetime.now(UTC) - timedelta(hours=1),
    )
    seed_db.add(cluster)
    seed_db.flush()
    source_item = SourceItem(
        source_type="news",
        source_name="MockWire",
        external_id="admin-1",
        url="https://example.test/admin-1",
        title="NVIDIA raises guidance",
        body_text="Management raised guidance after stronger demand.",
        published_at=datetime.now(UTC) - timedelta(hours=1),
        content_hash="admin-1",
        cluster_id="cluster-admin-1",
        is_representative=True,
        metadata_json={"symbols": ["NVDA"]},
    )
    seed_db.add(source_item)
    seed_db.add(
        ClusterSummary(
            cluster_id="cluster-admin-1",
            summary_text="NVIDIA raised guidance after stronger demand.",
            model_name="gpt-5-mini",
            prompt_version="cluster_summary_v2",
            structured_payload_json={"headline": "NVIDIA raises guidance"},
        )
    )
    digest = Digest(
        watchlist_id=1,
        run_date=date(2026, 4, 6),
        subject_line="Morning Brief — 1 item | NVDA",
        digest_markdown="# brief",
        digest_html="<p>brief</p>",
        delivery_status="generated",
        generated_at=datetime.now(UTC),
    )
    seed_db.add(digest)
    seed_db.flush()
    seed_db.add(
        DigestEntry(
            digest_id=digest.id,
            cluster_id=cluster.id,
            section_name="Must Know",
            rank=1,
            rationale_json={"importance_score": 0.91, "section_reason": "High importance and confidence."},
        )
    )
    seed_db.add(
        PipelineRun(
            run_type="ranking",
            status="success",
            watchlist_id=1,
            trigger_type="manual",
            provider_used="local",
            started_at=datetime.now(UTC) - timedelta(minutes=2),
            completed_at=datetime.now(UTC) - timedelta(minutes=1),
            metrics_json={"ranked_count": 1},
        )
    )
    seed_db.commit()
    seed_db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            runs = client.get("/admin/pipeline-runs")
            source_items = client.get("/admin/source-items")
            cluster_detail = client.get("/admin/clusters/cluster-admin-1")
            summaries = client.get("/admin/summaries")
            digests = client.get("/admin/digests")

            assert runs.status_code == 200
            assert source_items.status_code == 200
            assert cluster_detail.status_code == 200
            assert summaries.status_code == 200
            assert digests.status_code == 200

            cluster_payload = cluster_detail.json()
            assert cluster_payload["importance_score"] == 0.91
            assert cluster_payload["digest_sections"][0]["section_name"] == "Must Know"
            assert cluster_payload["summary"]["model_name"] == "gpt-5-mini"
    finally:
        app.dependency_overrides.clear()


def test_evaluation_runner_is_deterministic_and_exposes_summary_sanity() -> None:
    first = run_local_evaluations()
    second = run_local_evaluations()

    assert first["clustering_results"]["metrics"] == second["clustering_results"]["metrics"]
    assert first["classifier_results"]["metrics"] == second["classifier_results"]["metrics"]
    assert first["ranking_results"]["metrics"] == second["ranking_results"]["metrics"]
    assert first["summary_results"]["metrics"]["invalid_count"] == 1
    assert "cited_source_indices out of bounds" in first["summary_results"]["metrics"]["issues"][0]
