"""FastAPI application entrypoint."""

from fastapi import FastAPI

from backend.app.api.routes.health import router as health_router
from backend.app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Backend service scaffold for the After Market Agent project.",
    debug=settings.debug,
)

app.include_router(health_router)
