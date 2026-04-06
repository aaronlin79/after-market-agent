"""Job execution routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.schemas.digests import MorningRunRequest
from backend.app.services.scheduler.morning_run_service import run_morning_digest_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/morning-run")
def run_morning_job(payload: MorningRunRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Execute the full morning run immediately."""

    try:
        return run_morning_digest_job(db, watchlist_id=payload.watchlist_id, settings=get_settings())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
