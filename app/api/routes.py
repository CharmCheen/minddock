"""HTTP routes for base service endpoints."""

import logging

from fastapi import APIRouter

from app.api.schemas import ChatRequest, ChatResponse, SearchRequest, SearchResponse
from app.core.config import get_settings
from app.services.chat_service import ChatService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)
router = APIRouter()
search_service = SearchService()
chat_service = ChatService()


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
    result = search_service.search(query=payload.query, top_k=payload.top_k)
    return SearchResponse(**result)


@router.post("/chat", response_model=ChatResponse, summary="Minimal grounded chat")
def chat(payload: ChatRequest) -> ChatResponse:
    logger.debug("Chat endpoint called", extra={"top_k": payload.top_k})
    result = chat_service.chat(query=payload.query, top_k=payload.top_k)
    return ChatResponse(**result)
