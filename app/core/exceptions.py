"""Unified exception definitions and FastAPI exception handlers."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ServiceError(Exception):
    """Base exception for all service-layer errors."""

    status_code: int = 500
    error_category: str = "service_error"

    def __init__(self, detail: str = "An internal error occurred") -> None:
        self.detail = detail
        super().__init__(detail)


class IngestError(ServiceError):
    """Raised when document ingestion fails."""

    status_code: int = 500
    error_category: str = "ingest_error"


class SearchError(ServiceError):
    """Raised when search fails."""

    status_code: int = 500
    error_category: str = "search_error"


class ChatError(ServiceError):
    """Raised when chat generation fails."""

    status_code: int = 500
    error_category: str = "chat_error"


# ---------------------------------------------------------------------------
# FastAPI exception handler registration
# ---------------------------------------------------------------------------

def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers so routes stay clean."""

    @app.exception_handler(ServiceError)
    async def handle_service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.error(
            "Service error: category=%s detail=%s request_id=%s",
            exc.error_category,
            exc.detail,
            request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_category,
                "detail": exc.detail,
                "request_id": request_id,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.exception(
            "Unexpected error: request_id=%s",
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred. Check logs for details.",
                "request_id": request_id,
            },
        )
