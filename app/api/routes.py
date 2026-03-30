"""HTTP routes for all service endpoints."""

import logging

from fastapi import APIRouter

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SummarizeRequest,
    SummarizeResponse,
)
from app.core.config import get_settings
from app.services.chat_service import ChatService
from app.services.ingest_service import IngestService
from app.services.search_service import SearchService
from app.services.summarize_service import SummarizeService

logger = logging.getLogger(__name__)
router = APIRouter()

search_service = SearchService()
chat_service = ChatService()
summarize_service = SummarizeService()
ingest_service = IngestService()


# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

@router.post("/ingest", response_model=IngestResponse, summary="Ingest knowledge base documents")
def ingest(payload: IngestRequest) -> IngestResponse:
    logger.info("Ingest endpoint called: rebuild=%s", payload.rebuild)
    result = ingest_service.ingest(rebuild=payload.rebuild)
    return IngestResponse(**result)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SearchResponse, summary="Semantic search with citations")
def search(payload: SearchRequest) -> SearchResponse:
    logger.debug("Search endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.model_dump(exclude_none=True) if payload.filters else None
    result = search_service.search(query=payload.query, top_k=payload.top_k, filters=filters)
    return SearchResponse(**result)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse, summary="Grounded chat with citations")
def chat(payload: ChatRequest) -> ChatResponse:
    logger.debug("Chat endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.model_dump(exclude_none=True) if payload.filters else None
    result = chat_service.chat(query=payload.query, top_k=payload.top_k, filters=filters)
    return ChatResponse(**result)


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

@router.post("/summarize", response_model=SummarizeResponse, summary="Grounded summarization")
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    logger.debug("Summarize endpoint called: top_k=%d", payload.top_k)
    filters = payload.filters.model_dump(exclude_none=True) if payload.filters else None
    result = summarize_service.summarize(topic=payload.resolved_topic(), top_k=payload.top_k, filters=filters)
    return SummarizeResponse(**result)
