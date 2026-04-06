"""Unit tests for retrieval domain models and filter semantics."""

from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.services.grounded_generation import build_citation, build_context


def test_retrieved_chunk_preserves_original_text_for_citation() -> None:
    chunk = RetrievedChunk(
        text="compressed text",
        original_text="original text for citation",
        compressed_text="compressed text",
        doc_id="d1",
        chunk_id="c1",
        source="doc.md",
    )

    citation = build_citation(chunk)
    context = build_context([chunk])

    assert citation.snippet == "original text for citation"
    assert context.to_evidence_items()[0]["text"] == "compressed text"


def test_retrieval_filters_support_multi_source_and_contains_and_page_range() -> None:
    filters = RetrievalFilters(
        sources=("a.md", "https://example.com/final"),
        source_types=("file", "url"),
        title_contains="storage",
        requested_url_contains="example.com",
        page_from=2,
        page_to=4,
    )

    assert filters.matches_metadata(
        {
            "source": "https://example.com/final",
            "source_type": "url",
            "title": "Storage design",
            "requested_url": "https://example.com/requested",
            "page": 3,
        }
    )
    assert not filters.matches_metadata(
        {
            "source": "https://example.com/final",
            "source_type": "url",
            "title": "Storage design",
            "requested_url": "https://example.com/requested",
            "page": 8,
        }
    )
