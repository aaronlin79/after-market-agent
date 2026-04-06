"""In-process scheduler setup."""

from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

from backend.app.core.config import Settings, get_settings
from backend.app.core.db import SessionLocal
from backend.app.services.scheduler.morning_run_service import run_morning_digest_job

logger = logging.getLogger(__name__)

_scheduler: Any | None = None


def start_scheduler_if_enabled(settings: Settings | None = None) -> bool:
    """Start the scheduler only when enabled by config."""

    global _scheduler

    resolved_settings = settings or get_settings()
    if not resolved_settings.enable_scheduler:
        logger.info("Scheduler startup skipped because ENABLE_SCHEDULER is false.")
        return False
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler startup skipped because it is already running.")
        return False

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "APScheduler is required when ENABLE_SCHEDULER is true. Install project dependencies first."
        ) from exc

    timezone = ZoneInfo(resolved_settings.digest_timezone)
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        _run_scheduled_job,
        CronTrigger(hour=resolved_settings.digest_send_hour, minute=0, timezone=timezone),
        kwargs={"watchlist_id": resolved_settings.scheduled_watchlist_id},
        id="morning_digest_job",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started watchlist_id=%s timezone=%s hour=%s",
        resolved_settings.scheduled_watchlist_id,
        resolved_settings.digest_timezone,
        resolved_settings.digest_send_hour,
    )
    return True


def shutdown_scheduler() -> None:
    """Stop the in-process scheduler if it is running."""

    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped.")


def is_scheduler_running() -> bool:
    """Return whether the scheduler is active."""

    return _scheduler is not None and _scheduler.running


def _run_scheduled_job(watchlist_id: int) -> None:
    """Run the scheduled morning job in a fresh DB session."""

    db = SessionLocal()
    try:
        run_morning_digest_job(db, watchlist_id=watchlist_id)
    finally:
        db.close()
