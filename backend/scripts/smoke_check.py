"""Lightweight MVP smoke check for local readiness."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app

SAMPLE_SYMBOLS = [
    {"symbol": "NVDA", "company_name": "NVIDIA Corporation", "sector": "Semiconductors", "priority_weight": 1.0},
    {"symbol": "AMD", "company_name": "Advanced Micro Devices", "sector": "Semiconductors", "priority_weight": 1.0},
]


def main() -> None:
    client = TestClient(app)

    root_response = client.get("/")
    _assert_ok(root_response.status_code, "Frontend shell failed to load.")

    watchlists_response = client.get("/watchlists")
    _assert_ok(watchlists_response.status_code, "Watchlists endpoint failed.")
    watchlists = watchlists_response.json()

    if watchlists:
        watchlist_id = int(watchlists[0]["id"])
    else:
        create_response = client.post(
            "/watchlists",
            json={"name": "Smoke Check Watchlist", "description": "Created by smoke check."},
        )
        _assert_ok(create_response.status_code, "Could not create a smoke-check watchlist.", expected={201})
        watchlist_id = int(create_response.json()["id"])

    watchlist_detail = client.get(f"/watchlists/{watchlist_id}")
    _assert_ok(watchlist_detail.status_code, "Could not load the selected watchlist.")
    detail_payload = watchlist_detail.json()

    if not detail_payload.get("symbols"):
        for symbol_payload in SAMPLE_SYMBOLS:
            add_symbol_response = client.post(f"/watchlists/{watchlist_id}/symbols", json=symbol_payload)
            _assert_ok(
                add_symbol_response.status_code,
                f"Could not add sample symbol {symbol_payload['symbol']}.",
                expected={201, 409},
            )

    run_response = client.post("/jobs/morning-run", json={"watchlist_id": watchlist_id})
    _assert_ok(run_response.status_code, "Morning run failed.")
    run_payload = run_response.json()

    digests_response = client.get("/digests")
    _assert_ok(digests_response.status_code, "Digest list endpoint failed.")
    digests = digests_response.json()
    if run_payload.get("digest_id") is not None:
        digest_response = client.get(f"/digests/{run_payload['digest_id']}")
        _assert_ok(digest_response.status_code, "Latest digest detail failed.")

    print("Smoke check passed.")
    print(f"watchlist_id={watchlist_id}")
    print(f"digests_found={len(digests)}")
    print(f"run_result={run_payload}")


def _assert_ok(status_code: int, message: str, *, expected: set[int] | None = None) -> None:
    accepted = expected or {200}
    if status_code not in accepted:
        raise SystemExit(f"{message} Received status {status_code}.")


if __name__ == "__main__":
    main()
