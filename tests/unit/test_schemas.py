"""Unit tests for Pydantic request/response schemas."""

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    ChatRequest,
    CitationItem,
    ErrorResponse,
    IngestRequest,
    IngestResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)


# ---------------------------------------------------------------------------
# SearchRequest / ChatRequest
# ---------------------------------------------------------------------------

def test_search_request_rejects_blank_query() -> None:
    with pytest.raises(ValidationError, match="query must not be empty"):
        SearchRequest(query="   ")


def test_chat_request_trims_query() -> None:
    payload = ChatRequest(query="  hello  ")
    assert payload.query == "hello"


# ---------------------------------------------------------------------------
# CitationItem
# ---------------------------------------------------------------------------

def test_citation_item_requires_core_fields() -> None:
    citation = CitationItem(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="some snippet text",
    )
    assert citation.doc_id == "d1"
    assert citation.page is None
    assert citation.anchor is None
    assert citation.title is None
    assert citation.section is None
    assert citation.location is None
    assert citation.ref is None


def test_citation_item_accepts_page_and_anchor() -> None:
    citation = CitationItem(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="some snippet text",
        page=42,
        anchor="section-intro",
    )
    assert citation.page == 42
    assert citation.anchor == "section-intro"


def test_citation_item_page_is_int_not_string() -> None:
    """page must be int | None, not str."""
    citation = CitationItem(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="text",
        page=3,
    )
    assert isinstance(citation.page, int)


# ---------------------------------------------------------------------------
# SearchHit embeds CitationItem
# ---------------------------------------------------------------------------

def test_search_hit_carries_citation() -> None:
    citation = CitationItem(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="snippet",
    )
    hit = SearchHit(
        text="full chunk text",
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        distance=0.15,
        citation=citation,
    )
    assert hit.citation.snippet == "snippet"
    assert hit.citation.page is None


def test_search_response_contains_hits_with_citations() -> None:
    citation = CitationItem(
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        snippet="snippet",
    )
    resp = SearchResponse(
        query="test",
        top_k=1,
        hits=[
            SearchHit(
                text="text",
                doc_id="d1",
                chunk_id="c1",
                source="kb/doc.md",
                citation=citation,
            )
        ],
    )
    assert len(resp.hits) == 1
    assert resp.hits[0].citation.doc_id == "d1"


# ---------------------------------------------------------------------------
# Ingest schemas
# ---------------------------------------------------------------------------

def test_ingest_request_defaults_to_no_rebuild() -> None:
    req = IngestRequest()
    assert req.rebuild is False


def test_ingest_response_fields() -> None:
    resp = IngestResponse(documents=3, chunks=15)
    assert resp.documents == 3
    assert resp.chunks == 15


# ---------------------------------------------------------------------------
# Error schema
# ---------------------------------------------------------------------------

def test_error_response_structure() -> None:
    err = ErrorResponse(
        error="search_error",
        detail="Something went wrong",
        request_id="abc123",
    )
    assert err.error == "search_error"
    assert err.request_id == "abc123"


def test_error_response_request_id_optional() -> None:
    err = ErrorResponse(error="internal_error", detail="fail")
    assert err.request_id is None
