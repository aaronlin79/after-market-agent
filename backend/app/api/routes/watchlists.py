"""Watchlist API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.schemas.watchlists import (
    WatchlistCreate,
    WatchlistListResponse,
    WatchlistResponse,
    WatchlistSymbolCreate,
    WatchlistSymbolResponse,
    WatchlistUpdate,
)
from backend.app.services import watchlist_service

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=list[WatchlistListResponse])
def list_watchlists(db: Session = Depends(get_db)) -> list[WatchlistListResponse]:
    """Return all watchlists."""

    watchlists = watchlist_service.list_watchlists(db)
    return [
        WatchlistListResponse.model_validate(
            {
                "id": watchlist.id,
                "name": watchlist.name,
                "description": watchlist.description,
                "created_at": watchlist.created_at,
                "updated_at": watchlist.updated_at,
                "symbol_count": symbol_count,
            }
        )
        for watchlist, symbol_count in watchlists
    ]


@router.post("", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
def create_watchlist(
    payload: WatchlistCreate,
    db: Session = Depends(get_db),
) -> WatchlistResponse:
    """Create a watchlist."""

    watchlist = watchlist_service.create_watchlist(db, payload)
    return WatchlistResponse.model_validate(watchlist_service.get_watchlist(db, watchlist.id))


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
def get_watchlist(watchlist_id: int, db: Session = Depends(get_db)) -> WatchlistResponse:
    """Return one watchlist and its symbols."""

    try:
        watchlist = watchlist_service.get_watchlist(db, watchlist_id)
    except watchlist_service.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return WatchlistResponse.model_validate(watchlist)


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
def update_watchlist(
    watchlist_id: int,
    payload: WatchlistUpdate,
    db: Session = Depends(get_db),
) -> WatchlistResponse:
    """Update watchlist fields."""

    try:
        watchlist = watchlist_service.update_watchlist(db, watchlist_id, payload)
    except watchlist_service.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return WatchlistResponse.model_validate(watchlist)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(watchlist_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a watchlist."""

    try:
        watchlist_service.delete_watchlist(db, watchlist_id)
    except watchlist_service.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{watchlist_id}/symbols",
    response_model=WatchlistSymbolResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_symbol(
    watchlist_id: int,
    payload: WatchlistSymbolCreate,
    db: Session = Depends(get_db),
) -> WatchlistSymbolResponse:
    """Add a symbol to a watchlist."""

    try:
        symbol = watchlist_service.add_symbol(db, watchlist_id, payload)
    except watchlist_service.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except watchlist_service.DuplicateWatchlistSymbolError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return WatchlistSymbolResponse.model_validate(symbol)


@router.delete(
    "/{watchlist_id}/symbols/{symbol_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_symbol(
    watchlist_id: int,
    symbol_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Remove a symbol from a watchlist."""

    try:
        watchlist_service.remove_symbol(db, watchlist_id, symbol_id)
    except watchlist_service.WatchlistSymbolNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
