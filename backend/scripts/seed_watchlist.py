"""Seed a default watchlist with sample symbols."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import SessionLocal
from backend.app.schemas.watchlists import WatchlistCreate, WatchlistSymbolCreate
from backend.app.services import watchlist_service

SAMPLE_SYMBOLS = [
    {"symbol": "NVDA", "company_name": "NVIDIA Corporation"},
    {"symbol": "AMD", "company_name": "Advanced Micro Devices, Inc."},
    {"symbol": "MSFT", "company_name": "Microsoft Corporation"},
    {"symbol": "AAPL", "company_name": "Apple Inc."},
    {"symbol": "AMZN", "company_name": "Amazon.com, Inc."},
]


def seed_default_watchlist(db: Session) -> None:
    """Create the default watchlist and sample symbols if missing."""

    settings = get_settings()
    watchlist = watchlist_service.get_watchlist_by_name(db, settings.default_watchlist_name)

    if watchlist is None:
        watchlist = watchlist_service.create_watchlist(
            db,
            WatchlistCreate(name=settings.default_watchlist_name, description="Default seeded watchlist"),
        )
        print(f"Created watchlist: {watchlist.name}")
    else:
        print(f"Skipped existing watchlist: {watchlist.name}")

    existing_symbols = {symbol.symbol for symbol in watchlist_service.get_watchlist(db, watchlist.id).symbols}

    for symbol_data in SAMPLE_SYMBOLS:
        if symbol_data["symbol"] in existing_symbols:
            print(f"Skipped existing symbol: {symbol_data['symbol']}")
            continue

        created_symbol = watchlist_service.add_symbol(db, watchlist.id, WatchlistSymbolCreate(**symbol_data))
        print(f"Created symbol: {created_symbol.symbol}")


def main() -> None:
    """Run the watchlist seed script."""

    db = SessionLocal()
    try:
        seed_default_watchlist(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
