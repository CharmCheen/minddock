"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class MetadataFilters(BaseModel):
    """Minimal metadata filters shared by search and chat endpoints."""

    source: str | None = Field(default=None, description="Filter by document source path")
    section: str | None = Field(default=None, description="Filter by section heading")

    @field_validator("source", "section")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


# ---------------------------------------------------------------------------
# Citation
# ---------------------------------------------------------------------------

class CitationItem(BaseModel):
    """Standardized citation bound to a retrieved chunk.

    Required fields: doc_id, chunk_id, source, snippet.
    Optional fields preserved for compatibility and future expansion.
    """

    doc_id: str
    chunk_id: str
    source: str
    snippet: str
    page: int | None = None
    anchor: str | None = None
    title: str | None = None
    section: str | None = None
    location: str | None = None
    ref: str | None = None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchRequest(BaseModel):
    """Request body for the search endpoint."""

    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of hits to return")
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class SearchHit(BaseModel):
    """Single search result with its embedded citation."""

    text: str
    doc_id: str
    chunk_id: str
    source: str
    distance: float | None = None
    citation: CitationItem


class SearchResponse(BaseModel):
    """Response body for the search endpoint."""

    query: str
    top_k: int
    hits: list[SearchHit]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of retrieved chunks")
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class ChatResponse(BaseModel):
    """Response body for the chat endpoint."""

    answer: str
    citations: list[CitationItem]
    retrieved_count: int


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

class SummarizeRequest(BaseModel):
    """Request body for the summarize endpoint."""

    query: str | None = Field(default=None, description="Summary query or theme")
    topic: str | None = Field(default=None, description="Topic to summarize")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of retrieved chunks")
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")

    @field_validator("query", "topic")
    @classmethod
    def normalize_summary_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_topic_or_query(self) -> "SummarizeRequest":
        if not self.query and not self.topic:
            raise ValueError("either query or topic must be provided")
        return self

    def resolved_topic(self) -> str:
        return self.topic or self.query or ""


class SummarizeResponse(BaseModel):
    """Response body for the summarize endpoint."""

    summary: str
    citations: list[CitationItem]
    retrieved_count: int


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    """Request body for the ingest endpoint."""

    rebuild: bool = Field(default=False, description="Delete existing index before re-ingesting")


class IngestResponse(BaseModel):
    """Response body for the ingest endpoint."""

    documents: int = Field(description="Number of source documents processed")
    chunks: int = Field(description="Total chunks written to the vector store")


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Structured error response returned by all endpoints on failure."""

    error: str = Field(description="Machine-readable error category")
    detail: str = Field(description="Human-readable description")
    request_id: str | None = Field(default=None, description="Optional request trace id")
