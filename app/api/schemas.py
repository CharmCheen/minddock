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


class CitationItem(BaseModel):
    """Citation bound to a retrieved chunk."""

    doc_id: str
    chunk_id: str
    source: str
    snippet: str
    title: str | None = None
    section: str | None = None
    location: str | None = None
    ref: str | None = None


class SearchRequest(BaseModel):
    """Request body for the minimal search endpoint."""

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
    filters: MetadataFilters | None = Field(default=None, description="Optional metadata filters")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("query must not be empty")
        return query


class ChatResponse(BaseModel):
    """Response body for the minimal chat endpoint."""

    answer: str
    citations: list[CitationItem]
    retrieved_count: int


class SummarizeRequest(BaseModel):
    """Request body for the minimal summarize endpoint."""

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
    """Response body for the minimal summarize endpoint."""

    summary: str
    citations: list[CitationItem]
    retrieved_count: int
