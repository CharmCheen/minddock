"""Unit tests for application-layer service result models."""

from app.rag.retrieval_models import CitationRecord, SearchResult
from app.rag.source_models import FailedSourceInfo, IngestBatchResult, IngestSourceResult, SourceDescriptor
from app.services.service_models import (
    ChatServiceResult,
    IngestServiceResult,
    ServiceIssue,
    SearchServiceResult,
    SummarizeServiceResult,
    UseCaseMetadata,
    UseCaseTiming,
)


def test_search_service_result_exposes_search_result_and_metadata() -> None:
    result = SearchServiceResult(
        search_result=SearchResult(query="q", top_k=1, hits=[]),
        metadata=UseCaseMetadata(retrieved_count=0),
    )

    assert result.query == "q"
    assert result.top_k == 1
    assert result.to_api_dict()["hits"] == []


def test_chat_and_summarize_service_results_serialize_metadata() -> None:
    citation = CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text")

    chat = ChatServiceResult(
        answer="answer",
        citations=[citation],
        metadata=UseCaseMetadata(
            retrieved_count=1,
            mode="grounded",
            warnings=("warning",),
            issues=(ServiceIssue(code="insufficient_evidence", message="warning", severity="info"),),
            timing=UseCaseTiming(total_ms=8.5),
        ),
    )
    summarize = SummarizeServiceResult(
        summary="summary",
        citations=[citation],
        metadata=UseCaseMetadata(retrieved_count=1, mode="map_reduce", output_format="mermaid"),
        structured_output="mindmap",
    )

    assert chat.to_api_dict()["mode"] == "grounded"
    assert summarize.to_api_dict()["output_format"] == "mermaid"
    assert chat.metadata.issues[0].code == "insufficient_evidence"
    assert chat.metadata.timing.total_ms == 8.5


def test_ingest_service_result_serializes_partial_failure() -> None:
    result = IngestServiceResult(
        batch=IngestBatchResult(
            source_results=[
                IngestSourceResult(
                    descriptor=SourceDescriptor(source="doc.md", source_type="file"),
                    ok=True,
                    chunks_upserted=1,
                ),
                IngestSourceResult(
                    descriptor=SourceDescriptor(source="https://example.com", source_type="url"),
                    ok=False,
                    failure=FailedSourceInfo(
                        source="https://example.com",
                        source_type="url",
                        reason="network failed",
                    ),
                ),
            ]
        ),
        metadata=UseCaseMetadata(partial_failure=True),
    )

    payload = result.to_api_dict()

    assert payload["documents"] == 1
    assert payload["partial_failure"] is True
    assert payload["failed_sources"][0]["source_type"] == "url"
