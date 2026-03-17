"""HTTP routes for base service endpoints."""

import logging

from fastapi import APIRouter

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    SearchRequest,
    SearchResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from app.core.config import get_settings
from app.services.chat_service import ChatService
from app.services.search_service import SearchService
from app.services.summarize_service import SummarizeService

logger = logging.getLogger(__name__)
router = APIRouter()
search_service = SearchService()
chat_service = ChatService()
summarize_service = SummarizeService()


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


@router.post("/search", response_model=SearchResponse, summary="Minimal semantic search")
def search(payload: SearchRequest) -> SearchResponse:
    logger.debug("Search endpoint called", extra={"top_k": payload.top_k})
    filters = payload.filters.model_dump(exclude_none=True) if payload.filters else None
    result = search_service.search(query=payload.query, top_k=payload.top_k, filters=filters)
    return SearchResponse(**result)


@router.post("/chat", response_model=ChatResponse, summary="Minimal grounded chat")
def chat(payload: ChatRequest) -> ChatResponse:
    logger.debug("Chat endpoint called", extra={"top_k": payload.top_k})
    filters = payload.filters.model_dump(exclude_none=True) if payload.filters else None
    result = chat_service.chat(query=payload.query, top_k=payload.top_k, filters=filters)
    return ChatResponse(**result)


@router.post("/summarize", response_model=SummarizeResponse, summary="Minimal grounded summarization")
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    logger.debug("Summarize endpoint called", extra={"top_k": payload.top_k})
    filters = payload.filters.model_dump(exclude_none=True) if payload.filters else None
    result = summarize_service.summarize(topic=payload.resolved_topic(), top_k=payload.top_k, filters=filters)
    return SummarizeResponse(**result)
