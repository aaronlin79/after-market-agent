"""Watchlist service layer."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.models import Watchlist, WatchlistSymbol
from backend.app.schemas.watchlists import WatchlistCreate, WatchlistSymbolCreate, WatchlistUpdate


class WatchlistNotFoundError(Exception):
    """Raised when a watchlist does not exist."""


class WatchlistSymbolNotFoundError(Exception):
    """Raised when a watchlist symbol does not exist."""


class DuplicateWatchlistSymbolError(Exception):
    """Raised when a symbol already exists on a watchlist."""


def create_watchlist(db: Session, payload: WatchlistCreate) -> Watchlist:
    """Create and persist a watchlist."""

    watchlist = Watchlist(name=payload.name, description=payload.description)
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    return watchlist


def list_watchlists(db: Session) -> list[tuple[Watchlist, int]]:
    """Return all watchlists with symbol counts."""

    statement = (
        select(Watchlist, func.count(WatchlistSymbol.id))
        .outerjoin(WatchlistSymbol, Watchlist.id == WatchlistSymbol.watchlist_id)
        .group_by(Watchlist.id)
        .order_by(Watchlist.name.asc())
    )
    return list(db.execute(statement).all())


def get_watchlist(db: Session, watchlist_id: int) -> Watchlist:
    """Return a watchlist with its symbols."""

    statement = (
        select(Watchlist)
        .options(selectinload(Watchlist.symbols))
        .where(Watchlist.id == watchlist_id)
    )
    watchlist = db.execute(statement).scalar_one_or_none()
    if watchlist is None:
        raise WatchlistNotFoundError(f"Watchlist {watchlist_id} was not found.")

    watchlist.symbols.sort(key=lambda symbol: symbol.symbol)
    return watchlist


def get_watchlist_by_name(db: Session, name: str) -> Watchlist | None:
    """Return a watchlist by name."""

    statement = select(Watchlist).where(Watchlist.name == name)
    return db.execute(statement).scalar_one_or_none()


def update_watchlist(db: Session, watchlist_id: int, payload: WatchlistUpdate) -> Watchlist:
    """Update a watchlist name and description."""

    watchlist = get_watchlist(db, watchlist_id)
    updates = payload.model_dump(exclude_unset=True)

    for field_name, value in updates.items():
        setattr(watchlist, field_name, value)

    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    watchlist.symbols.sort(key=lambda symbol: symbol.symbol)
    return watchlist


def delete_watchlist(db: Session, watchlist_id: int) -> None:
    """Delete a watchlist and its related symbols."""

    watchlist = get_watchlist(db, watchlist_id)
    db.delete(watchlist)
    db.commit()


def add_symbol(db: Session, watchlist_id: int, payload: WatchlistSymbolCreate) -> WatchlistSymbol:
    """Add a symbol to a watchlist."""

    get_watchlist(db, watchlist_id)

    symbol = WatchlistSymbol(
        watchlist_id=watchlist_id,
        symbol=payload.symbol,
        company_name=payload.company_name,
        sector=payload.sector,
        priority_weight=payload.priority_weight,
    )
    db.add(symbol)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateWatchlistSymbolError(
            f"Symbol {payload.symbol} already exists on watchlist {watchlist_id}."
        ) from exc

    db.refresh(symbol)
    return symbol


def remove_symbol(db: Session, watchlist_id: int, symbol_id: int) -> None:
    """Remove a symbol from a watchlist."""

    statement = select(WatchlistSymbol).where(
        WatchlistSymbol.id == symbol_id,
        WatchlistSymbol.watchlist_id == watchlist_id,
    )
    symbol = db.execute(statement).scalar_one_or_none()
    if symbol is None:
        raise WatchlistSymbolNotFoundError(
            f"Symbol {symbol_id} was not found on watchlist {watchlist_id}."
        )

    db.delete(symbol)
    db.commit()
