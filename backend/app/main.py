"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from backend.app.api.routes.admin import router as admin_router
from backend.app.api.routes.clusters import router as clusters_router
from backend.app.api.routes.digests import router as digests_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.jobs import router as jobs_router
from backend.app.api.routes.pipelines import router as pipelines_router
from backend.app.api.routes.summaries import router as summaries_router
from backend.app.api.routes.watchlists import router as watchlists_router
from backend.app.core.config import get_settings
from backend.app.services.scheduler.scheduler_service import shutdown_scheduler, start_scheduler_if_enabled

settings = get_settings()


def _configure_logging() -> None:
    """Ensure application logs are visible in local development."""

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.DEBUG if settings.debug else logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    else:
        root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)


_configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manage app startup and shutdown resources."""

    start_scheduler_if_enabled(settings)
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(
    title=settings.app_name,
    description="Backend service scaffold for the After Market Agent project.",
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(admin_router)
app.include_router(clusters_router)
app.include_router(digests_router)
app.include_router(jobs_router)
app.include_router(pipelines_router)
app.include_router(summaries_router)
app.include_router(watchlists_router)
