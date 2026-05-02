"""Unit tests for retrieval domain models and filter semantics."""

from app.rag.retrieval_models import RetrievedChunk, RetrievalFilters
from app.services.grounded_generation import build_citation, build_context, build_evidence


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


def test_build_citation_derived_metadata_passthrough() -> None:
    chunk = RetrievedChunk(
        text="summary of the video transcript",
        original_text="summary of the video transcript",
        compressed_text="summary of the video transcript",
        doc_id="video-001",
        chunk_id="video-001:derived:summary",
        source="demo_video.mp4",
        extra_metadata={
            "is_derived": "true",
            "derived_kind": "media_summary",
            "derived_from": "transcript",
            "derived_basis": "transcript_text",
            "evidence_basis": "transcript_text",
            "transcript_provider": "sidecar",
            "retrieval_basis": "transcript_text",
        },
    )

    citation = build_citation(chunk)
    assert citation.is_derived is True
    assert citation.derived_kind == "media_summary"
    assert citation.derived_from == "transcript"
    assert citation.derived_basis == "transcript_text"
    assert citation.evidence_basis == "transcript_text"
    assert citation.transcript_provider == "sidecar"
    assert citation.retrieval_basis == "transcript_text"

    api_dict = citation.to_api_dict()
    assert api_dict["is_derived"] is True
    assert api_dict["derived_kind"] == "media_summary"
    assert api_dict["derived_from"] == "transcript"
    assert api_dict["evidence_basis"] == "transcript_text"
    assert api_dict["transcript_provider"] == "sidecar"
    assert api_dict["retrieval_basis"] == "transcript_text"


def test_build_evidence_derived_metadata_passthrough() -> None:
    chunk = RetrievedChunk(
        text="outline of video sections",
        original_text="outline of video sections",
        compressed_text="outline of video sections",
        doc_id="video-001",
        chunk_id="video-001:derived:outline",
        source="demo_video.mp4",
        extra_metadata={
            "is_derived": "true",
            "derived_kind": "media_outline",
            "derived_from": "transcript",
            "derived_basis": "transcript_text",
            "evidence_basis": "transcript_text",
            "transcript_provider": "mock",
            "retrieval_basis": "transcript_text",
        },
    )

    evidence = build_evidence(chunk)
    assert evidence.is_derived is True
    assert evidence.derived_kind == "media_outline"
    assert evidence.derived_from == "transcript"
    assert evidence.evidence_basis == "transcript_text"
    assert evidence.transcript_provider == "mock"
    assert evidence.retrieval_basis == "transcript_text"

    api_dict = evidence.to_api_dict()
    assert api_dict["is_derived"] is True
    assert api_dict["derived_kind"] == "media_outline"
    assert api_dict["derived_from"] == "transcript"
    assert api_dict["evidence_basis"] == "transcript_text"
    assert api_dict["transcript_provider"] == "mock"
    assert api_dict["retrieval_basis"] == "transcript_text"


def test_build_citation_non_derived_chunk_has_no_derived_fields() -> None:
    chunk = RetrievedChunk(
        text="plain text content",
        original_text="plain text content",
        compressed_text="plain text content",
        doc_id="doc-001",
        chunk_id="doc-001:chunk:1",
        source="readme.md",
        extra_metadata={"retrieval_basis": "text"},
    )

    citation = build_citation(chunk)
    assert citation.is_derived is False
    assert citation.derived_kind is None
    assert citation.derived_from is None
    assert citation.derived_basis is None
    assert citation.evidence_basis is None
    assert citation.transcript_provider is None
    assert citation.retrieval_basis == "text"

