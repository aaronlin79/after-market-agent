"""OpenAI summarization integration tests with mocked clients."""

from __future__ import annotations

import sys
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from types import ModuleType

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import Settings
from backend.app.models import ClusterSummary, SourceItem
from backend.app.models.base import Base
from backend.app.services.openai.openai_client import OpenAIResponsesClient
from backend.app.services.summarization.cluster_summary_service import generate_cluster_summaries
from backend.app.services.summarization.openai_cluster_summarizer import (
    ClusterSummaryStructuredOutput,
    build_source_packet,
    summarize_cluster_with_openai,
)


class FakeOpenAIClient:
    """Deterministic fake OpenAI client for tests."""

    def __init__(self, parsed_output: ClusterSummaryStructuredOutput | None = None, *, should_fail: bool = False) -> None:
        self.parsed_output = parsed_output
        self.should_fail = should_fail
        self.call_count = 0

    def parse_structured_output(self, *, instructions: str, input_text: str, response_model):
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("forced OpenAI failure")
        return self.parsed_output, "gpt-test-summary"


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


def _openai_settings() -> Settings:
    return Settings(
        app_name="After Market Agent",
        environment="test",
        database_url="sqlite://",
        debug=False,
        default_watchlist_name="Default Watchlist",
        email_provider="mock",
        email_api_key=None,
        email_from="digest@example.com",
        digest_recipients=["digest@example.com"],
        digest_timezone="America/Los_Angeles",
        digest_send_hour=6,
        enable_scheduler=False,
        scheduled_watchlist_id=1,
        openai_api_key="test-key",
        openai_model_summary="gpt-test-summary",
        openai_timeout_seconds=30,
        openai_max_retries=1,
        openai_max_clusters_per_run=25,
        openai_max_calls_per_run=25,
    )


def _seed_multiple_clustered_articles(db: Session, cluster_count: int) -> None:
    now = datetime.now(UTC)
    articles: list[SourceItem] = []
    for cluster_index in range(cluster_count):
        articles.append(
            SourceItem(
                source_type="news",
                source_name="MockWire",
                external_id=f"article-{cluster_index}",
                url=f"https://example.test/cluster-{cluster_index}",
                title=f"Cluster {cluster_index} headline",
                body_text=f"Cluster {cluster_index} body text with a concrete fact.",
                published_at=now - timedelta(hours=cluster_index + 1),
                content_hash=f"cluster-{cluster_index}",
                cluster_id=f"cluster-{cluster_index}",
                is_representative=True,
                metadata_json={},
            )
        )
    db.add_all(articles)
    db.commit()


def test_structured_response_parsing_works(db_session: Session) -> None:
    articles = _seed_clustered_articles(db_session)
    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="NVIDIA demand update remains constructive",
            summary_bullets=["Demand commentary remained constructive.", "Multiple reports pointed to supplier confidence."],
            why_it_matters="The sources point to demand stability heading into the next earnings cycle.",
            confidence="medium",
            unknowns=["No company guidance was cited directly."],
            cited_source_indices=[0, 1],
        )
    )

    result = summarize_cluster_with_openai(articles, settings=_openai_settings(), client=fake_client)

    assert result.headline == "NVIDIA demand update remains constructive"
    assert result.model_name == "gpt-test-summary"
    assert result.cited_source_indices == [0, 1]


def test_invalid_structured_output_is_handled_cleanly(db_session: Session) -> None:
    _seed_clustered_articles(db_session)
    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="NVIDIA demand update remains constructive",
            summary_bullets=["Demand commentary remained constructive."],
            why_it_matters="The sources point to demand stability.",
            confidence="medium",
            unknowns=[],
            cited_source_indices=[3],
        )
    )

    stats = generate_cluster_summaries(
        db_session,
        settings=_openai_settings(),
        openai_client=fake_client,
    )
    summary = db_session.execute(select(ClusterSummary)).scalar_one()

    assert stats["fallback_count"] == 1
    assert stats["baseline_count"] == 1
    assert summary.model_name == "baseline"


def test_openai_path_selected_when_key_present(db_session: Session) -> None:
    _seed_clustered_articles(db_session)
    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="NVIDIA demand update remains constructive",
            summary_bullets=["Demand commentary remained constructive."],
            why_it_matters="The sources point to demand stability.",
            confidence="medium",
            unknowns=[],
            cited_source_indices=[0],
        )
    )

    stats = generate_cluster_summaries(
        db_session,
        settings=_openai_settings(),
        openai_client=fake_client,
    )
    summary = db_session.execute(select(ClusterSummary)).scalar_one()

    assert stats["summarizer_used"] == "openai"
    assert stats["openai_count"] == 1
    assert summary.model_name == "gpt-test-summary"


def test_baseline_fallback_used_when_api_key_missing(db_session: Session) -> None:
    _seed_clustered_articles(db_session)
    settings = _openai_settings().model_copy(update={"openai_api_key": None})

    stats = generate_cluster_summaries(db_session, settings=settings)
    summary = db_session.execute(select(ClusterSummary)).scalar_one()

    assert stats["summarizer_used"] == "baseline"
    assert stats["baseline_count"] == 1
    assert summary.model_name == "baseline"


def test_baseline_fallback_used_when_openai_call_fails(db_session: Session) -> None:
    _seed_clustered_articles(db_session)

    stats = generate_cluster_summaries(
        db_session,
        settings=_openai_settings(),
        openai_client=FakeOpenAIClient(should_fail=True),
    )
    summary = db_session.execute(select(ClusterSummary)).scalar_one()

    assert stats["fallback_count"] == 1
    assert stats["summarizer_used"] == "baseline"
    assert summary.model_name == "baseline"
    assert summary.structured_payload_json is not None
    assert summary.structured_payload_json["summarizer_used"] == "baseline"
    assert "forced OpenAI failure" in summary.structured_payload_json["fallback_reason"]


def test_mocked_openai_summaries_are_deterministic(db_session: Session) -> None:
    articles = _seed_clustered_articles(db_session)
    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="NVIDIA demand update remains constructive",
            summary_bullets=["Demand commentary remained constructive."],
            why_it_matters="The sources point to demand stability.",
            confidence="medium",
            unknowns=["Direct company guidance was not quoted."],
            cited_source_indices=[0, 1],
        )
    )

    first = summarize_cluster_with_openai(articles, settings=_openai_settings(), client=fake_client)
    second = summarize_cluster_with_openai(list(reversed(articles)), settings=_openai_settings(), client=fake_client)

    assert first.rendered_summary_text == second.rendered_summary_text


def test_cited_source_indices_map_correctly_to_source_inputs(db_session: Session) -> None:
    articles = _seed_clustered_articles(db_session)
    packet = build_source_packet(articles)

    assert [source["source_index"] for source in packet] == [0, 1]

    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="NVIDIA demand update remains constructive",
            summary_bullets=["Demand commentary remained constructive."],
            why_it_matters="The sources point to demand stability.",
            confidence="medium",
            unknowns=[],
            cited_source_indices=[0, 1],
        )
    )
    generate_cluster_summaries(db_session, settings=_openai_settings(), openai_client=fake_client)
    summary = db_session.execute(select(ClusterSummary)).scalar_one()

    assert summary.structured_payload_json is not None
    assert summary.structured_payload_json["cited_source_indices"] == [0, 1]


def test_openai_client_uses_bounded_timeout_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeSDKClient:
        def __init__(self, *, api_key: str, timeout: float, max_retries: int) -> None:
            captured["api_key"] = api_key
            captured["timeout"] = timeout
            captured["max_retries"] = max_retries
            self.responses = object()

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeSDKClient
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    client = OpenAIResponsesClient(
        Settings(
            app_name="After Market Agent",
            environment="test",
            database_url="sqlite://",
            debug=False,
            default_watchlist_name="Default Watchlist",
            email_provider="mock",
            email_api_key=None,
            email_from="digest@example.com",
            digest_recipients=["digest@example.com"],
            digest_timezone="America/Los_Angeles",
            digest_send_hour=6,
            enable_scheduler=False,
            scheduled_watchlist_id=1,
            openai_api_key="test-key",
            openai_model_summary="gpt-test-summary",
            openai_timeout_seconds=0,
            openai_max_retries=-5,
            openai_max_clusters_per_run=25,
            openai_max_calls_per_run=25,
        )
    )

    assert client.timeout_seconds == 1.0
    assert client.max_retries == 0
    assert captured["timeout"] == 1.0
    assert captured["max_retries"] == 0


def test_max_cluster_limit_stops_further_processing(db_session: Session) -> None:
    _seed_multiple_clustered_articles(db_session, 3)
    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="Cluster headline",
            summary_bullets=["Cluster summary bullet."],
            why_it_matters="This matters for the watchlist.",
            confidence="medium",
            unknowns=[],
            cited_source_indices=[0],
        )
    )

    stats = generate_cluster_summaries(
        db_session,
        settings=_openai_settings().model_copy(update={"openai_max_clusters_per_run": 2}),
        openai_client=fake_client,
    )

    summaries = list(db_session.execute(select(ClusterSummary)).scalars())
    assert stats["clusters_processed"] == 2
    assert stats["skipped_due_to_limits"] == 1
    assert stats["openai_calls_made"] == 2
    assert fake_client.call_count == 2
    assert len(summaries) == 2


def test_max_call_limit_stops_further_openai_usage(db_session: Session) -> None:
    _seed_multiple_clustered_articles(db_session, 3)
    fake_client = FakeOpenAIClient(
        ClusterSummaryStructuredOutput(
            headline="Cluster headline",
            summary_bullets=["Cluster summary bullet."],
            why_it_matters="This matters for the watchlist.",
            confidence="medium",
            unknowns=[],
            cited_source_indices=[0],
        )
    )

    stats = generate_cluster_summaries(
        db_session,
        settings=_openai_settings().model_copy(update={"openai_max_calls_per_run": 1}),
        openai_client=fake_client,
    )

    summaries = list(db_session.execute(select(ClusterSummary)).scalars())
    baseline_models = [summary.model_name for summary in summaries if summary.model_name == "baseline"]

    assert stats["clusters_processed"] == 3
    assert stats["openai_calls_made"] == 1
    assert stats["baseline_count"] == 2
    assert stats["skipped_due_to_limits"] == 0
    assert fake_client.call_count == 1
    assert len(baseline_models) == 2
