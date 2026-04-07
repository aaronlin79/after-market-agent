"""Lightweight pipeline run tracking helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models import PipelineRun

logger = logging.getLogger(__name__)

SUCCESS = "success"
PARTIAL_SUCCESS = "partial_success"
FAILED = "failed"
RUNNING = "running"


def start_pipeline_run(
    db: Session,
    *,
    run_type: str,
    watchlist_id: int | None = None,
    trigger_type: str = "manual",
    provider_used: str | None = None,
    metrics_json: dict[str, Any] | None = None,
) -> PipelineRun:
    """Create and persist a running pipeline record."""

    run = PipelineRun(
        run_type=run_type,
        status=RUNNING,
        watchlist_id=watchlist_id,
        trigger_type=trigger_type,
        provider_used=provider_used,
        metrics_json=metrics_json or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "Pipeline run started id=%s run_type=%s watchlist_id=%s trigger_type=%s provider_used=%s",
        run.id,
        run.run_type,
        run.watchlist_id,
        run.trigger_type,
        run.provider_used,
    )
    return run


def complete_pipeline_run(
    db: Session,
    run: PipelineRun,
    *,
    status: str = SUCCESS,
    metrics_json: dict[str, Any] | None = None,
    error_message: str | None = None,
    provider_used: str | None = None,
) -> PipelineRun:
    """Mark a pipeline run complete and attach final metrics."""

    run.status = status
    run.completed_at = datetime.now(UTC)
    if metrics_json is not None:
        run.metrics_json = metrics_json
    if error_message is not None:
        run.error_message = error_message
    if provider_used is not None:
        run.provider_used = provider_used
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "Pipeline run completed id=%s run_type=%s status=%s duration_ms=%s",
        run.id,
        run.run_type,
        run.status,
        calculate_duration_ms(run),
    )
    return run


def fail_pipeline_run(
    db: Session,
    run: PipelineRun,
    *,
    error: Exception,
    metrics_json: dict[str, Any] | None = None,
    provider_used: str | None = None,
) -> PipelineRun:
    """Mark a pipeline run failed with an error message."""

    return complete_pipeline_run(
        db,
        run,
        status=FAILED,
        metrics_json=metrics_json,
        error_message=f"{type(error).__name__}: {error}",
        provider_used=provider_used,
    )


def calculate_duration_ms(run: PipelineRun) -> int | None:
    """Calculate run duration in milliseconds when complete."""

    if run.completed_at is None:
        return None
    started_at = run.started_at.astimezone(UTC) if run.started_at.tzinfo else run.started_at.replace(tzinfo=UTC)
    completed_at = run.completed_at.astimezone(UTC) if run.completed_at.tzinfo else run.completed_at.replace(tzinfo=UTC)
    return int((completed_at - started_at).total_seconds() * 1000)
