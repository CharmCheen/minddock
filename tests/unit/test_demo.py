"""Unit tests for demo serialization helpers."""

from app.demo import (
    _metadata_to_dict,
    _serialize_catalog_result,
    _serialize_delete_source_result,
    _serialize_chat_result,
    _serialize_ingest_result,
    _serialize_reingest_source_result,
    _serialize_search_result,
    _serialize_source_detail_result,
    _serialize_source_inspect_result,
    _serialize_summarize_result,
)
from app.rag.retrieval_models import CitationRecord, RetrievedChunk, SearchHitRecord, SearchResult
from app.rag.source_models import DeleteSourceResult, FailedSourceInfo, IngestBatchResult, IngestSourceResult, SourceCatalogEntry, SourceChunkPage, SourceChunkPreview, SourceDescriptor, SourceDetail, SourceInspectResult
from app.services.service_models import (
    CatalogServiceResult,
    ChatServiceResult,
    DeleteSourceServiceResult,
    IngestServiceResult,
    ReingestSourceServiceResult,
    SearchServiceResult,
    ServiceIssue,
    SourceStats,
    SourceDetailServiceResult,
    SourceInspectServiceResult,
    SummarizeServiceResult,
    UseCaseMetadata,
    UseCaseTiming,
)


def test_metadata_to_dict_includes_controlled_fields() -> None:
    payload = _metadata_to_dict(
        UseCaseMetadata(
            retrieved_count=1,
            warnings=("warning",),
            issues=(ServiceIssue(code="empty_result", message="no hits", severity="info"),),
            timing=UseCaseTiming(total_ms=12.5, retrieval_ms=4.0),
            filter_applied=True,
            source_stats=SourceStats(requested_sources=2, succeeded_sources=1, failed_sources=1),
        )
    )

    assert payload["warnings"] == ["warning"]
    assert payload["issues"][0]["code"] == "empty_result"
    assert payload["timing"]["total_ms"] == 12.5
    assert payload["source_stats"]["failed_sources"] == 1


def test_demo_serializers_consume_service_results() -> None:
    chunk = RetrievedChunk(text="text", doc_id="d1", chunk_id="c1", source="kb/doc.md")
    citation = CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text")

    search_payload = _serialize_search_result(
        SearchServiceResult(
            search_result=SearchResult(
                query="q",
                top_k=1,
                hits=[SearchHitRecord(chunk=chunk, citation=citation)],
            ),
            metadata=UseCaseMetadata(retrieved_count=1),
        )
    )
    chat_payload = _serialize_chat_result(
        ChatServiceResult(
            answer="answer",
            citations=[citation],
            metadata=UseCaseMetadata(retrieved_count=1, mode="grounded"),
        )
    )
    summarize_payload = _serialize_summarize_result(
        SummarizeServiceResult(
            summary="summary",
            citations=[citation],
            metadata=UseCaseMetadata(retrieved_count=1, mode="basic", output_format="text"),
        )
    )
    ingest_payload = _serialize_ingest_result(
        IngestServiceResult(
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
    )

    assert search_payload["hits"][0]["source"] == "kb/doc.md"
    assert chat_payload["mode"] == "grounded"
    assert summarize_payload["retrieved_count"] == 1
    assert ingest_payload["partial_failure"] is True


def test_demo_catalog_serializers() -> None:
    catalog_payload = _serialize_catalog_result(
        CatalogServiceResult(
            entries=[
                SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                )
            ]
        )
    )
    detail_payload = _serialize_source_detail_result(
        SourceDetailServiceResult(
            found=True,
            detail=SourceDetail(
                entry=SourceCatalogEntry(
                    doc_id="d1",
                    source="notes.md",
                    source_type="file",
                    title="notes",
                    chunk_count=2,
                ),
                representative_metadata={"title": "notes"},
            ),
        )
    )
    delete_payload = _serialize_delete_source_result(
        DeleteSourceServiceResult(result=DeleteSourceResult(found=True, doc_id="d1", source="notes.md", source_type="file", deleted_chunks=2))
    )
    reingest_payload = _serialize_reingest_source_result(
        ReingestSourceServiceResult(
            found=True,
            source_result=IngestSourceResult(
                descriptor=SourceDescriptor(source="notes.md", source_type="file"),
                ok=True,
                chunks_upserted=2,
                chunks_deleted=1,
            ),
        )
    )
    inspect_payload = _serialize_source_inspect_result(
        SourceInspectServiceResult(
            found=True,
            inspect=SourceInspectResult(
                detail=SourceDetail(
                    entry=SourceCatalogEntry(
                        doc_id="d1",
                        source="notes.md",
                        source_type="file",
                        title="notes",
                        chunk_count=2,
                    ),
                    representative_metadata={"title": "notes"},
                ),
                chunk_page=SourceChunkPage(
                    total_chunks=2,
                    returned_chunks=1,
                    limit=1,
                    offset=0,
                    chunks=[
                        SourceChunkPreview(
                            chunk_id="d1:0",
                            chunk_index=0,
                            preview_text="chunk preview",
                            title="notes",
                            section="Storage",
                            location="Storage",
                            ref="notes > Storage",
                            admin_metadata={"doc_id": "d1"},
                        )
                    ],
                ),
                include_admin_metadata=True,
                admin_metadata={"doc_id": "d1"},
            ),
        )
    )

    assert catalog_payload["total"] == 1
    assert detail_payload["item"]["source"] == "notes.md"
    assert delete_payload["deleted_chunks"] == 2
    assert reingest_payload["ok"] is True
    assert inspect_payload["chunks"][0]["chunk_id"] == "d1:0"
    assert inspect_payload["admin_metadata"]["doc_id"] == "d1"
