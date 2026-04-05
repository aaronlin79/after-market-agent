"""FastAPI application entrypoint."""

from fastapi import FastAPI

from backend.app.api.routes.clusters import router as clusters_router
from backend.app.api.routes.digests import router as digests_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.pipelines import router as pipelines_router
from backend.app.api.routes.summaries import router as summaries_router
from backend.app.api.routes.watchlists import router as watchlists_router
from backend.app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Backend service scaffold for the After Market Agent project.",
    debug=settings.debug,
)

app.include_router(health_router)
app.include_router(clusters_router)
app.include_router(digests_router)
app.include_router(pipelines_router)
app.include_router(summaries_router)
app.include_router(watchlists_router)
