"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.runtime.active_config import bootstrap_env_from_active_config

settings = get_settings()
setup_logging(settings.log_level, settings.log_dir, settings.app_name)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Log startup details using the supported FastAPI lifespan hook."""

    # Bootstrap user-configured runtime credentials into environment
    bootstrap_env_from_active_config()

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

# Allow frontend dev server origins (Vite default 5173, CRA default 3000, plus explicit localhost/127.0.0.1 variants)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
