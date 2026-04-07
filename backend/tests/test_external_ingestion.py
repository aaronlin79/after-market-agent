"""External ingestion tests with mocked provider payloads."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import Settings
from backend.app.models import SourceItem
from backend.app.models.base import Base
from backend.app.pipelines.news_pipeline import run_full_ingestion
from backend.app.services.news.adapters.finnhub_adapter import FinnhubNewsAdapter
from backend.app.services.news.news_ingestion_service import ingest_news
from backend.app.services.sec.sec_ingestion_service import ingest_sec_filings


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


def _settings(**updates: object) -> Settings:
    base = Settings(
        app_name="After Market Agent",
        environment="test",
        database_url="sqlite://",
        debug=False,
        default_watchlist_name="Default Watchlist",
        news_provider="mock",
        news_api_key=None,
        sec_user_agent="after-market-agent test@example.com",
        sec_api_key=None,
        ingestion_lookback_hours=24,
        email_provider="mock",
        email_api_key=None,
        email_from="digest@example.com",
        digest_recipients=["digest@example.com"],
        digest_timezone="America/Los_Angeles",
        digest_send_hour=6,
        enable_scheduler=False,
        scheduled_watchlist_id=1,
        openai_api_key=None,
        openai_model_summary="gpt-5-mini",
        openai_timeout_seconds=30,
        openai_max_retries=1,
        openai_max_clusters_per_run=25,
        openai_max_calls_per_run=25,
    )
    return base.model_copy(update=updates)


def test_finnhub_adapter_normalizes_provider_response() -> None:
    published_at = datetime(2026, 4, 6, 1, 0, tzinfo=UTC)

    def fake_fetch_json(url: str):
        assert "company-news" in url
        return [
            {
                "id": 12345,
                "datetime": int(published_at.timestamp()),
                "headline": "NVIDIA extends overnight gains",
                "summary": "Shares rose after a strong supplier read.",
                "source": "Reuters",
                "url": "https://example.test/nvda-gains",
                "category": "company",
                "image": "https://example.test/image.jpg",
                "related": "NVDA",
            }
        ]

    adapter = FinnhubNewsAdapter(
        settings=_settings(news_provider="finnhub", news_api_key="test-news-key"),
        fetch_json=fake_fetch_json,
    )

    items = adapter.fetch_news(
        symbols=["NVDA"],
        start_time=published_at - timedelta(hours=1),
        end_time=published_at + timedelta(hours=1),
    )

    assert len(items) == 1
    assert items[0]["external_id"] == "12345"
    assert items[0]["title"] == "NVIDIA extends overnight gains"
    assert items[0]["body_text"] == "Shares rose after a strong supplier read."
    assert items[0]["source_name"] == "Reuters"
    assert items[0]["metadata_json"]["provider"] == "finnhub"
    assert items[0]["metadata_json"]["symbol"] == "NVDA"


def test_sec_ingestion_normalizes_recent_filings(db_session: Session) -> None:
    filing_date = datetime(2026, 4, 6, tzinfo=UTC)

    def fake_fetch_json(url: str, headers: dict[str, str]):
        assert headers["User-Agent"] == "after-market-agent test@example.com"
        if "company_tickers.json" in url:
            return {
                "0": {"ticker": "NVDA", "cik_str": 1045810, "title": "NVIDIA CORP"},
            }
        return {
            "filings": {
                "recent": {
                    "accessionNumber": ["0001045810-26-000001"],
                    "filingDate": [filing_date.date().isoformat()],
                    "form": ["8-K"],
                    "primaryDocument": ["form8k.htm"],
                    "primaryDocDescription": ["Current report"],
                }
            }
        }

    stats = ingest_sec_filings(
        db=db_session,
        symbols=["NVDA"],
        start_time=filing_date - timedelta(days=1),
        end_time=filing_date + timedelta(days=1),
        settings=_settings(),
        fetch_json=fake_fetch_json,
    )

    item = db_session.execute(select(SourceItem)).scalar_one()
    assert stats["provider_used"] == "sec"
    assert stats["mapped_symbol_count"] == 1
    assert stats["fetched_count"] == 1
    assert stats["inserted_count"] == 1
    assert item.source_type == "filing"
    assert item.source_name == "sec"
    assert item.external_id == "0001045810-26-000001"
    assert item.metadata_json["form_type"] == "8-K"
    assert item.metadata_json["ticker"] == "NVDA"


def test_duplicate_skipping_works_for_filings(db_session: Session) -> None:
    filing_date = datetime(2026, 4, 6, tzinfo=UTC)

    def fake_fetch_json(url: str, headers: dict[str, str]):
        if "company_tickers.json" in url:
            return {"0": {"ticker": "AMD", "cik_str": 2488, "title": "ADVANCED MICRO DEVICES INC"}}
        return {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000002488-26-000001"],
                    "filingDate": [filing_date.date().isoformat()],
                    "form": ["10-Q"],
                    "primaryDocument": ["amd10q.htm"],
                    "primaryDocDescription": ["Quarterly report"],
                }
            }
        }

    first = ingest_sec_filings(
        db=db_session,
        symbols=["AMD"],
        start_time=filing_date - timedelta(days=1),
        end_time=filing_date + timedelta(days=1),
        settings=_settings(),
        fetch_json=fake_fetch_json,
    )
    second = ingest_sec_filings(
        db=db_session,
        symbols=["AMD"],
        start_time=filing_date - timedelta(days=1),
        end_time=filing_date + timedelta(days=1),
        settings=_settings(),
        fetch_json=fake_fetch_json,
    )

    count = db_session.execute(select(func.count(SourceItem.id))).scalar_one()
    assert first["inserted_count"] == 1
    assert second["inserted_count"] == 0
    assert second["skipped_duplicates"] == 1
    assert count == 1


def test_full_ingest_returns_combined_stats(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    monkeypatch.setattr(
        "backend.app.pipelines.news_pipeline.get_watchlist_symbols",
        lambda db, watchlist_id=None: ["NVDA", "AMD"],
    )
    monkeypatch.setattr(
        "backend.app.pipelines.news_pipeline.ingest_news",
        lambda **kwargs: {
            "provider_used": "finnhub",
            "fetched_count": 4,
            "inserted_count": 3,
            "skipped_duplicates": 1,
        },
    )
    monkeypatch.setattr(
        "backend.app.pipelines.news_pipeline.ingest_sec_filings",
        lambda **kwargs: {
            "provider_used": "sec",
            "mapped_symbol_count": 2,
            "fetched_count": 2,
            "inserted_count": 2,
            "skipped_duplicates": 0,
        },
    )

    stats = run_full_ingestion(db_session, watchlist_id=1, settings=_settings(news_provider="finnhub"))

    assert stats["watchlist_id"] == 1
    assert stats["provider_used"] == "finnhub"
    assert stats["news_fetched_count"] == 4
    assert stats["news_inserted_count"] == 3
    assert stats["filing_fetched_count"] == 2
    assert stats["filing_inserted_count"] == 2
    assert stats["skipped_duplicates"] == 1
    assert stats["news_error"] is None
    assert stats["sec_error"] is None


def test_partial_failure_allows_other_source_to_continue(monkeypatch: pytest.MonkeyPatch, db_session: Session) -> None:
    monkeypatch.setattr(
        "backend.app.pipelines.news_pipeline.get_watchlist_symbols",
        lambda db, watchlist_id=None: ["NVDA"],
    )

    def fail_news(**kwargs):
        raise RuntimeError("news provider offline")

    monkeypatch.setattr("backend.app.pipelines.news_pipeline.ingest_news", fail_news)
    monkeypatch.setattr(
        "backend.app.pipelines.news_pipeline.ingest_sec_filings",
        lambda **kwargs: {
            "provider_used": "sec",
            "mapped_symbol_count": 1,
            "fetched_count": 1,
            "inserted_count": 1,
            "skipped_duplicates": 0,
        },
    )

    stats = run_full_ingestion(db_session, watchlist_id=1, settings=_settings(news_provider="finnhub"))

    assert stats["news_error"] == "RuntimeError: news provider offline"
    assert stats["sec_error"] is None
    assert stats["filing_inserted_count"] == 1
    assert stats["news_inserted_count"] == 0


def test_config_validation_is_clear_when_provider_settings_are_missing(db_session: Session) -> None:
    with pytest.raises(ValueError, match="NEWS_API_KEY"):
        FinnhubNewsAdapter(settings=_settings(news_provider="finnhub", news_api_key=None))

    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        ingest_sec_filings(
            db=db_session,
            symbols=["NVDA"],
            start_time=datetime.now(UTC) - timedelta(hours=1),
            end_time=datetime.now(UTC),
            settings=_settings(sec_user_agent=None),
            fetch_json=lambda url, headers: {},
        )


def test_news_ingestion_uses_real_provider_when_selected(db_session: Session) -> None:
    published_at = datetime(2026, 4, 6, 1, 0, tzinfo=UTC)

    def fake_fetch_json(url: str):
        return [
            {
                "id": 10,
                "datetime": int(published_at.timestamp()),
                "headline": "AMD moves after product launch",
                "summary": "",
                "source": "Reuters",
                "url": "https://example.test/amd-launch",
                "category": "company",
                "image": "",
                "related": "AMD",
            }
        ]

    stats = ingest_news(
        db=db_session,
        symbols=["AMD"],
        start_time=published_at - timedelta(hours=1),
        end_time=published_at + timedelta(hours=1),
        adapter=FinnhubNewsAdapter(
            settings=_settings(news_provider="finnhub", news_api_key="test-news-key"),
            fetch_json=fake_fetch_json,
        ),
        settings=_settings(news_provider="finnhub", news_api_key="test-news-key"),
    )

    item = db_session.execute(select(SourceItem)).scalar_one()
    assert stats["provider_used"] == "finnhub"
    assert stats["inserted_count"] == 1
    assert item.source_type == "news"
    assert item.metadata_json["provider"] == "finnhub"
