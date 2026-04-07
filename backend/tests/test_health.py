"""Health endpoint tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_health_endpoint_returns_ok() -> None:
    """Health endpoint should report an operational service."""

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
