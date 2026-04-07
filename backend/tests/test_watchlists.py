"""Watchlist API tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models.base import Base


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
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_create_watchlist(client: TestClient) -> None:
    """Create a watchlist successfully."""

    response = client.post("/watchlists", json={"name": "Core List", "description": "Main coverage"})

    assert response.status_code == 201
    assert response.json()["name"] == "Core List"
    assert response.json()["description"] == "Main coverage"
    assert response.json()["symbols"] == []


def test_list_watchlists(client: TestClient) -> None:
    """List existing watchlists."""

    client.post("/watchlists", json={"name": "Growth", "description": "Growth names"})
    client.post("/watchlists", json={"name": "Value", "description": "Value names"})

    response = client.get("/watchlists")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert [item["name"] for item in payload] == ["Growth", "Value"]
    assert [item["symbol_count"] for item in payload] == [0, 0]


def test_get_watchlist_with_symbols(client: TestClient) -> None:
    """Return one watchlist with related symbols."""

    watchlist = client.post("/watchlists", json={"name": "Tech", "description": "Tech names"}).json()
    client.post(
        f"/watchlists/{watchlist['id']}/symbols",
        json={"symbol": "msft", "company_name": "Microsoft Corporation"},
    )
    client.post(
        f"/watchlists/{watchlist['id']}/symbols",
        json={"symbol": "AAPL", "company_name": "Apple Inc."},
    )

    response = client.get(f"/watchlists/{watchlist['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == watchlist["id"]
    assert [item["symbol"] for item in payload["symbols"]] == ["AAPL", "MSFT"]


def test_add_symbol_normalizes_symbol(client: TestClient) -> None:
    """Add a symbol to a watchlist and normalize the ticker."""

    watchlist = client.post("/watchlists", json={"name": "Semis", "description": None}).json()

    response = client.post(
        f"/watchlists/{watchlist['id']}/symbols",
        json={"symbol": "nvda", "company_name": "NVIDIA Corporation", "priority_weight": 2.0},
    )

    assert response.status_code == 201
    assert response.json()["symbol"] == "NVDA"
    assert response.json()["priority_weight"] == 2.0


def test_duplicate_symbol_rejected(client: TestClient) -> None:
    """Reject duplicate symbols within the same watchlist."""

    watchlist = client.post("/watchlists", json={"name": "Duplicates", "description": None}).json()
    client.post(
        f"/watchlists/{watchlist['id']}/symbols",
        json={"symbol": "AMD", "company_name": "Advanced Micro Devices, Inc."},
    )

    response = client.post(
        f"/watchlists/{watchlist['id']}/symbols",
        json={"symbol": "amd", "company_name": "Advanced Micro Devices, Inc."},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_delete_symbol(client: TestClient) -> None:
    """Delete a symbol from a watchlist."""

    watchlist = client.post("/watchlists", json={"name": "Delete Symbol", "description": None}).json()
    symbol = client.post(
        f"/watchlists/{watchlist['id']}/symbols",
        json={"symbol": "AMZN", "company_name": "Amazon.com, Inc."},
    ).json()

    response = client.delete(f"/watchlists/{watchlist['id']}/symbols/{symbol['id']}")

    assert response.status_code == 204
    watchlist_response = client.get(f"/watchlists/{watchlist['id']}")
    assert watchlist_response.json()["symbols"] == []


def test_delete_watchlist(client: TestClient) -> None:
    """Delete a watchlist successfully."""

    watchlist = client.post("/watchlists", json={"name": "Delete Me", "description": None}).json()

    response = client.delete(f"/watchlists/{watchlist['id']}")

    assert response.status_code == 204
    missing_response = client.get(f"/watchlists/{watchlist['id']}")
    assert missing_response.status_code == 404


def test_missing_watchlist_returns_404(client: TestClient) -> None:
    """Return 404 for missing watchlists."""

    response = client.get("/watchlists/999")

    assert response.status_code == 404
