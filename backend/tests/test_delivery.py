"""Email delivery and scheduler tests."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import Settings
from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models import ClusterSummary, Digest, StoryCluster, Watchlist, WatchlistSymbol
from backend.app.models.base import Base
from backend.app.services.digest.digest_service import generate_morning_digest
from backend.app.services.email.brevo_provider import BrevoEmailProvider
from backend.app.services.email.email_service import _get_email_provider, send_digest_email
from backend.app.services.email.resend_provider import ResendEmailProvider
from backend.app.services.scheduler.scheduler_service import is_scheduler_running, shutdown_scheduler, start_scheduler_if_enabled


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


def _seed_watchlist_and_cluster(db: Session) -> tuple[int, int]:
    watchlist = Watchlist(name="Delivery Watchlist", description="delivery")
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    db.add(WatchlistSymbol(watchlist_id=watchlist.id, symbol="NVDA", company_name="NVIDIA Corporation"))
    db.commit()
    now = datetime.now(UTC)
    cluster = StoryCluster(
        cluster_key="cluster-delivery",
        representative_title="NVDA raises guidance after earnings",
        primary_symbol="NVDA",
        event_type="earnings",
        importance_score=0.92,
        novelty_score=0.8,
        credibility_score=0.8,
        confidence="high",
        first_seen_at=now - timedelta(hours=2),
        last_seen_at=now - timedelta(hours=1),
    )
    db.add(cluster)
    db.commit()
    db.add(ClusterSummary(cluster_id="cluster-delivery", summary_text="NVIDIA raised guidance after earnings."))
    db.commit()
    digest = generate_morning_digest(db, watchlist.id)
    return watchlist.id, digest["digest_id"]


def test_mock_email_provider_sends_successfully(db_session: Session) -> None:
    _, digest_id = _seed_watchlist_and_cluster(db_session)
    settings = Settings(
        app_name="After Market Agent",
        environment="test",
        database_url="sqlite://",
        debug=False,
        default_watchlist_name="Default Watchlist",
        email_provider="mock",
        email_api_key=None,
        email_from="digest@example.com",
        digest_recipients=["alice@example.com", "bob@example.com"],
        digest_timezone="America/Los_Angeles",
        digest_send_hour=6,
        enable_scheduler=False,
        scheduled_watchlist_id=1,
    )

    result = send_digest_email(db_session, digest_id=digest_id, settings=settings)

    assert result["delivery_status"] == "sent"
    assert result["provider"] == "mock"
    assert result["recipient_count"] == 2


def test_sending_digest_updates_delivery_status_and_sent_at(db_session: Session) -> None:
    _, digest_id = _seed_watchlist_and_cluster(db_session)
    settings = Settings(
        app_name="After Market Agent",
        environment="test",
        database_url="sqlite://",
        debug=False,
        default_watchlist_name="Default Watchlist",
        email_provider="mock",
        email_api_key=None,
        email_from="digest@example.com",
        digest_recipients=["alice@example.com"],
        digest_timezone="America/Los_Angeles",
        digest_send_hour=6,
        enable_scheduler=False,
        scheduled_watchlist_id=1,
    )

    send_digest_email(db_session, digest_id=digest_id, settings=settings)
    digest = db_session.get(Digest, digest_id)

    assert digest is not None
    assert digest.delivery_status == "sent"
    assert digest.sent_at is not None


def test_missing_digest_returns_404(client: TestClient) -> None:
    response = client.post("/digests/999/send")
    assert response.status_code == 404


def test_invalid_email_provider_config_fails_clearly(db_session: Session) -> None:
    _, digest_id = _seed_watchlist_and_cluster(db_session)
    settings = Settings(
        app_name="After Market Agent",
        environment="test",
        database_url="sqlite://",
        debug=False,
        default_watchlist_name="Default Watchlist",
        email_provider="unknown",
        email_api_key=None,
        email_from="digest@example.com",
        digest_recipients=["alice@example.com"],
        digest_timezone="America/Los_Angeles",
        digest_send_hour=6,
        enable_scheduler=False,
        scheduled_watchlist_id=1,
    )

    with pytest.raises(ValueError, match="Unsupported EMAIL_PROVIDER"):
        send_digest_email(db_session, digest_id=digest_id, settings=settings)


def test_provider_selection_uses_brevo_by_default() -> None:
    settings = Settings(
        email_provider="brevo",
        brevo_api_key="brevo-key",
        resend_api_key="resend-key",
        email_from="digest@example.com",
        email_from_name="After Market Agent",
        digest_recipients=["alice@example.com"],
    )

    provider = _get_email_provider(settings)

    assert isinstance(provider, BrevoEmailProvider)


def test_missing_brevo_api_key_fails_clearly() -> None:
    settings = Settings(
        email_provider="brevo",
        brevo_api_key=None,
        email_from="digest@example.com",
        email_from_name="After Market Agent",
        digest_recipients=["alice@example.com"],
    )

    with pytest.raises(ValueError, match="BREVO_API_KEY"):
        _get_email_provider(settings)


def test_preserved_resend_path_is_selectable() -> None:
    settings = Settings(
        email_provider="resend",
        resend_api_key="resend-key",
        email_from="digest@example.com",
        email_from_name="After Market Agent",
        digest_recipients=["alice@example.com"],
    )

    provider = _get_email_provider(settings)

    assert isinstance(provider, ResendEmailProvider)


def test_successful_brevo_send_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResponse:
        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"messageId":"brevo-message-123"}'

    def fake_urlopen(_request):
        return DummyResponse()

    monkeypatch.setattr("backend.app.services.email.brevo_provider.request.urlopen", fake_urlopen)

    provider = BrevoEmailProvider(
        api_key="brevo-key",
        from_address="digest@example.com",
        from_name="After Market Agent",
    )

    result = provider.send_email(
        to=["alice@example.com"],
        subject="Morning Brief",
        html="<p>Hello</p>",
        text="Hello",
    )

    assert result["provider"] == "brevo"
    assert result["status"] == "sent"
    assert result["message_id"] == "brevo-message-123"


def test_manual_morning_run_endpoint_executes_end_to_end(client: TestClient, db_session: Session) -> None:
    watchlist_id, _ = _seed_watchlist_and_cluster(db_session)

    response = client.post("/jobs/morning-run", json={"watchlist_id": watchlist_id})

    assert response.status_code == 200
    payload = response.json()
    assert payload["digest_id"] is not None
    assert payload["emailed"] is True
    assert payload["delivery_status"] == "sent"


def test_scheduler_startup_is_skipped_when_disabled() -> None:
    shutdown_scheduler()
    settings = Settings(
        app_name="After Market Agent",
        environment="test",
        database_url="sqlite://",
        debug=False,
        default_watchlist_name="Default Watchlist",
        email_provider="mock",
        email_api_key=None,
        email_from="digest@example.com",
        digest_recipients=["alice@example.com"],
        digest_timezone="America/Los_Angeles",
        digest_send_hour=6,
        enable_scheduler=False,
        scheduled_watchlist_id=1,
    )

    started = start_scheduler_if_enabled(settings=settings)

    assert started is False
    assert is_scheduler_running() is False
