"""Frontend smoke tests."""

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_root_serves_mvp_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "After Market Agent" in response.text
    assert "/ui/app.js" in response.text
