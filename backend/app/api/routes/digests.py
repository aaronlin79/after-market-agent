"""Digest generation and retrieval routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.schemas.digests import DigestGenerateRequest
from backend.app.services.digest.digest_service import generate_morning_digest, get_digest, list_digests
from backend.app.services.email.email_service import send_digest_email

router = APIRouter(prefix="/digests", tags=["digests"])


@router.post("/generate")
def generate_digest(payload: DigestGenerateRequest, db: Session = Depends(get_db)) -> dict:
    """Generate a morning digest for a watchlist."""

    try:
        return generate_morning_digest(db, payload.watchlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("")
def get_digests(db: Session = Depends(get_db)) -> list[dict]:
    """List generated digests newest first."""

    return list_digests(db)


@router.get("/{digest_id}")
def get_digest_by_id(digest_id: int, db: Session = Depends(get_db)) -> dict:
    """Return a full stored digest."""

    digest = get_digest(db, digest_id)
    if digest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Digest {digest_id} was not found.")
    return digest


@router.post("/{digest_id}/send")
def send_digest(digest_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Send a stored digest by email."""

    try:
        return send_digest_email(db, digest_id=digest_id, settings=get_settings())
    except ValueError as exc:
        detail = str(exc)
        status_code = status.HTTP_404_NOT_FOUND if "was not found" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
