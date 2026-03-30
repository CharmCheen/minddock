"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.log_level, settings.log_dir, settings.app_name)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Log startup details using the supported FastAPI lifespan hook."""

    logger.info(
        "Service starting",
        extra={
            "service": settings.app_name,
            "version": settings.app_version,
            "log_level": settings.log_level,
            "log_dir": settings.log_dir,
        },
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

register_exception_handlers(app)
app.include_router(api_router)
