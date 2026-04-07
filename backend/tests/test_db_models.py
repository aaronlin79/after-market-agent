"""Database model tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import Watchlist, WatchlistSymbol
from backend.app.models.base import Base


@pytest.fixture()
def db_session() -> Session:
    """Create an isolated SQLite session for database tests."""

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_tables_create_and_watchlist_symbol_unique_constraint(db_session: Session) -> None:
    """Tables should create cleanly and enforce watchlist symbol uniqueness."""

    watchlist = Watchlist(name="Core Watchlist", description="Primary symbols")
    db_session.add(watchlist)
    db_session.flush()

    db_session.add(
        WatchlistSymbol(
            watchlist_id=watchlist.id,
            symbol="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            priority_weight=1.5,
        )
    )
    db_session.commit()

    inserted_symbol = db_session.query(WatchlistSymbol).filter_by(symbol="AAPL").one()
    assert inserted_symbol.company_name == "Apple Inc."
    assert inserted_symbol.created_at is not None

    db_session.add(
        WatchlistSymbol(
            watchlist_id=watchlist.id,
            symbol="AAPL",
            company_name="Apple Inc.",
            sector="Technology",
            priority_weight=1.0,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
