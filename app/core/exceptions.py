"""Unified exception definitions and FastAPI exception handlers."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.presenters import present_error_response

logger = logging.getLogger(__name__)


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


class SummarizeError(ServiceError):
    """Raised when grounded summarization fails."""

    status_code: int = 500
    error_category: str = "summarize_error"


class UnifiedExecutionError(ServiceError):
    """Raised when a unified execution request cannot be satisfied."""

    status_code: int = 400
    error_category: str = "unified_execution_error"


class RuntimeCapabilityMismatchError(UnifiedExecutionError):
    """Raised when a requested runtime cannot satisfy the required capabilities."""

    status_code: int = 400
    error_category: str = "runtime_capability_mismatch"


class RuntimeProfileNotFoundError(UnifiedExecutionError):
    """Raised when a requested runtime profile does not exist."""

    status_code: int = 404
    error_category: str = "runtime_profile_not_found"


class RuntimeProfileDisabledError(UnifiedExecutionError):
    """Raised when a requested runtime profile is disabled."""

    status_code: int = 400
    error_category: str = "runtime_profile_disabled"


class RuntimeProfileCapabilityMismatchError(UnifiedExecutionError):
    """Raised when a runtime profile cannot satisfy required capabilities."""

    status_code: int = 400
    error_category: str = "runtime_profile_capability_mismatch"


class RuntimeResolutionFailedError(UnifiedExecutionError):
    """Raised when runtime resolution fails after evaluating available profiles."""

    status_code: int = 400
    error_category: str = "runtime_resolution_failed"


class RuntimeProfileInvalidConfigError(UnifiedExecutionError):
    """Raised when runtime profile configuration is invalid."""

    status_code: int = 500
    error_category: str = "runtime_profile_invalid_config"


class UnsupportedExecutionModeError(UnifiedExecutionError):
    """Raised when a task or output mode is unsupported."""

    status_code: int = 400
    error_category: str = "unsupported_execution_mode"


class SkillNotAllowedError(UnifiedExecutionError):
    """Raised when a skill is requested outside the active skill policy."""

    status_code: int = 400
    error_category: str = "skill_not_allowed"


class SkillNotFoundError(UnifiedExecutionError):
    """Raised when a requested skill cannot be found in the registry."""

    status_code: int = 404
    error_category: str = "skill_not_found"


class SkillDisabledError(UnifiedExecutionError):
    """Raised when a requested skill exists but is disabled."""

    status_code: int = 400
    error_category: str = "skill_disabled"


class SkillNotAllowlistedError(UnifiedExecutionError):
    """Raised when a requested skill is not permitted by the active skill policy."""

    status_code: int = 400
    error_category: str = "skill_not_allowlisted"


class SkillNotPublicError(UnifiedExecutionError):
    """Raised when a skill is hidden from public listing under the active policy."""

    status_code: int = 403
    error_category: str = "skill_not_public"


class SkillInvocationModeMismatchError(UnifiedExecutionError):
    """Raised when invocation source and descriptor/policy modes do not match."""

    status_code: int = 400
    error_category: str = "skill_invocation_mode_mismatch"


class InvalidSkillInputError(UnifiedExecutionError):
    """Raised when skill arguments fail typed input validation."""

    status_code: int = 422
    error_category: str = "invalid_skill_input"


class SkillExecutionFailedError(UnifiedExecutionError):
    """Raised when a skill fails during execution."""

    status_code: int = 500
    error_category: str = "skill_execution_failed"


class RunNotFoundError(UnifiedExecutionError):
    """Raised when a transient execution run cannot be found."""

    status_code: int = 404
    error_category: str = "run_not_found"


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
        payload = present_error_response(
            error=exc.error_category,
            category=exc.error_category,
            detail=exc.detail,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        issues = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", []))
            message = str(item.get("msg", "invalid value"))
            issues.append(f"{location}: {message}")
        detail = "; ".join(issues) or "Request validation failed"
        logger.warning("Validation error: detail=%s request_id=%s", detail, request_id)
        payload = present_error_response(
            error="validation_error",
            category="validation_error",
            detail=detail,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=422,
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        request_id = uuid.uuid4().hex[:12]
        logger.exception(
            "Unexpected error: request_id=%s",
            request_id,
        )
        payload = present_error_response(
            error="internal_error",
            category="internal_error",
            detail="An unexpected error occurred. Check logs for details.",
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content=payload.model_dump(),
        )
