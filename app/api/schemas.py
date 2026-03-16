"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    """Request body for the minimal search endpoint."""

    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of hits to return")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class SearchHit(BaseModel):
    """Minimal search hit returned by the API."""

    text: str
    doc_id: str
    chunk_id: str
    source: str
    distance: float | None = None


class SearchResponse(BaseModel):
    """Response body for the minimal search endpoint."""

    query: str
    top_k: int
    hits: list[SearchHit]


class ChatRequest(BaseModel):
    """Request body for the minimal chat endpoint."""

    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of retrieved chunks")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class CitationItem(BaseModel):
    """Citation bound to a retrieved chunk."""

    doc_id: str
    chunk_id: str
    source: str
    snippet: str


class ChatResponse(BaseModel):
    """Response body for the minimal chat endpoint."""

    answer: str
    citations: list[CitationItem]
    retrieved_count: int
