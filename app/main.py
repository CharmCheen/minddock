"""FastAPI application entrypoint."""

import logging

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    """Log startup details to aid debugging."""

    logger.info(
        "Service starting",
        extra={
            "service": settings.app_name,
            "version": settings.app_version,
            "log_level": settings.log_level,
        },
    )
