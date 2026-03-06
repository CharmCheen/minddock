"""HTTP routes for base service endpoints."""

import logging

from fastapi import APIRouter

from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="Service info")
def root() -> dict[str, str]:
    settings = get_settings()
    logger.debug("Root endpoint called")
    return {
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/health", summary="Health check")
def health() -> dict[str, str]:
    settings = get_settings()
    logger.debug("Health endpoint called")
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }
