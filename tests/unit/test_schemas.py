"""Unit tests for Pydantic request/response schemas."""

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    CitationItem,
    DeleteSourceResponse,
    ErrorResponse,
    IngestRequest,
    IngestResponse,
    MetadataFilters,
    ReingestSourceResponse,
    RuntimeProfileListResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceCatalogItem,
    SourceCatalogQueryParams,
    SourceCatalogResponse,
    SourceChunkPageResponse,
    SourceInspectQueryParams,
    SourceDetailResponse,
    SourceLookupParams,
    SummarizeRequest,
    SummarizeResponse,
    UnifiedExecutionRequestBody,
)
from app.runtime.models import RuntimeProfileSummary
from app.rag.retrieval_models import CitationRecord, RetrievedChunk, SearchHitRecord, SearchResult
from app.rag.source_models import (
    DeleteSourceResult,
    FailedSourceInfo,
    IngestBatchResult,
    IngestSourceResult,
    SourceCatalogEntry,
    SourceChunkPage,
    SourceChunkPreview,
    SourceDescriptor,
    SourceDetail,
    SourceInspectResult,
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


def test_metadata_filters_support_multi_value_and_contains() -> None:
    filters = MetadataFilters(
        source=[" kb/doc.md ", "https://example.com"],
        source_type=["file", "url"],
        title_contains="  storage ",
        requested_url_contains=" example.com ",
        page_from=1,
        page_to=3,
    )
    spec = filters.to_retrieval_filters()
    assert spec.sources == ("kb/doc.md", "https://example.com")
    assert spec.source_types == ("file", "url")
    assert spec.title_contains == "storage"
    assert spec.requested_url_contains == "example.com"


def test_metadata_filters_reject_invalid_page_range() -> None:
    with pytest.raises(ValidationError, match="page_from must be less than or equal to page_to"):
        MetadataFilters(page_from=5, page_to=2)


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


def test_search_response_can_be_built_from_formal_result() -> None:
    chunk = RetrievedChunk(
        text="text",
        doc_id="d1",
        chunk_id="c1",
        source="kb/doc.md",
        source_type="file",
        title="Doc",
        section="Storage",
        distance=0.2,
    )
    result = SearchResult(
        query="test",
        top_k=1,
        hits=[
            SearchHitRecord(
                chunk=chunk,
                citation=CitationRecord(
                    doc_id="d1",
                    chunk_id="c1",
                    source="kb/doc.md",
                    snippet="text",
                    section="Storage",
                ),
            )
        ],
    )

    response = SearchResponse.from_result(result)

    assert response.hits[0].source_type == "file"
    assert response.hits[0].title == "Doc"
    assert response.hits[0].section == "Storage"


# ---------------------------------------------------------------------------
# Ingest schemas
# ---------------------------------------------------------------------------

def test_ingest_request_defaults_to_no_rebuild() -> None:
    req = IngestRequest()
    assert req.rebuild is False
    assert req.urls == []


def test_ingest_request_normalizes_urls() -> None:
    req = IngestRequest(urls=[" https://example.com/page ", "http://example.com/other"])
    assert req.urls == ["https://example.com/page", "http://example.com/other"]


def test_ingest_request_rejects_non_http_urls() -> None:
    with pytest.raises(ValidationError, match="ingest urls must start with http:// or https://"):
        IngestRequest(urls=["ftp://example.com"])


def test_ingest_response_fields() -> None:
    resp = IngestResponse(documents=3, chunks=15)
    assert resp.documents == 3
    assert resp.chunks == 15
    assert resp.ingested_sources == []
    assert resp.failed_sources == []
    assert resp.partial_failure is False


def test_ingest_response_can_be_built_from_batch_result() -> None:
    result = IngestBatchResult(
        source_results=[
            IngestSourceResult(
                descriptor=SourceDescriptor(source="doc.md", source_type="file"),
                ok=True,
                chunks_upserted=2,
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
    )

    response = IngestResponse.from_result(result)

    assert response.documents == 1
    assert response.partial_failure is True
    assert response.failed_sources[0].source_type == "url"


def test_source_catalog_query_and_lookup_params() -> None:
    assert SourceCatalogQueryParams(source_type="file").source_type == "file"
    assert SourceLookupParams(source=" notes.md ").source == "notes.md"
    assert SourceInspectQueryParams(limit=5, offset=2, include_admin_metadata=True).limit == 5


def test_catalog_detail_delete_and_reingest_responses() -> None:
    item = SourceCatalogItem.from_entry(
        SourceCatalogEntry(
            doc_id="d1",
            source="notes.md",
            source_type="file",
            title="notes",
            chunk_count=2,
            sections=("Storage",),
        )
    )
    catalog = SourceCatalogResponse(items=[item], total=1)
    detail = SourceDetailResponse.from_result(
        type(
            "DetailResult",
            (),
            {
                "found": True,
                "detail": SourceDetail(entry=_item_to_entry(item), representative_metadata={"title": "notes"}),
                "include_admin_metadata": False,
                "admin_metadata": {},
            },
        )()
    )
    delete = DeleteSourceResponse.from_result(
        DeleteSourceResult(found=True, doc_id="d1", source="notes.md", source_type="file", deleted_chunks=2)
    )
    reingest = ReingestSourceResponse.from_result(
        type(
            "ReingestResult",
            (),
            {
                "found": True,
                "source_result": IngestSourceResult(
                    descriptor=SourceDescriptor(source="notes.md", source_type="file"),
                    ok=True,
                    chunks_upserted=2,
                    chunks_deleted=1,
                ),
            },
        )()
    )

    assert catalog.total == 1
    assert detail.item is not None and detail.item.source == "notes.md"
    assert delete.deleted_chunks == 2
    assert reingest.ok is True


def test_source_chunk_page_response_serializes_admin_metadata() -> None:
    response = SourceChunkPageResponse.from_result(
        type(
            "InspectResult",
            (),
            {
                "found": True,
                "inspect": SourceInspectResult(
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
                        offset=1,
                        chunks=[
                            SourceChunkPreview(
                                chunk_id="d1:1",
                                chunk_index=1,
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
                    admin_metadata={"doc_id": "d1", "chunk_count": 2},
                ),
            },
        )()
    )

    assert response.total_chunks == 2
    assert response.chunks[0].chunk_index == 1
    assert response.admin_metadata["chunk_count"] == 2


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
    assert err.category is None


def test_error_response_from_parts_sets_category_by_default() -> None:
    err = ErrorResponse.from_parts(error="search_error", detail="failed", request_id="abc")
    assert err.error == "search_error"
    assert err.category == "search_error"


def test_summarize_request_defaults_mode_and_output_format() -> None:
    payload = SummarizeRequest(topic="storage")
    assert payload.mode == "basic"
    assert payload.output_format == "text"


def test_summarize_response_accepts_structured_output() -> None:
    resp = SummarizeResponse(
        summary="summary",
        evidence=[{"doc_id": "d1", "chunk_id": "c1", "source": "kb/doc.md", "snippet": "text"}],
        support_status="supported",
        citations=[],
        retrieved_count=1,
        mode="map_reduce",
        output_format="mermaid",
        structured_output="mindmap\n  root[\"storage\"]",
    )
    assert resp.output_format == "mermaid"
    assert resp.structured_output is not None


def test_chat_response_from_result_defaults_mode() -> None:
    resp = ChatResponse.from_result(
        {
            "answer": "answer",
            "citations": [{"doc_id": "d1", "chunk_id": "c1", "source": "kb/doc.md", "snippet": "text"}],
            "retrieved_count": 1,
        }
    )
    assert resp.mode == "grounded"
    assert resp.support_status == "supported"
    assert resp.evidence[0].chunk_id == "c1"


def test_chat_response_from_result_exposes_refusal_semantics() -> None:
    resp = ChatResponse.from_result(
        {
            "answer": "Insufficient evidence to answer.",
            "citations": [],
            "retrieved_count": 0,
            "insufficient_evidence": True,
            "support_status": "insufficient_evidence",
            "refusal_reason": "no_relevant_evidence",
        }
    )
    assert resp.support_status == "insufficient_evidence"
    assert resp.refusal_reason == "no_relevant_evidence"
    assert resp.evidence == []


def test_unified_execution_request_supports_execution_policy() -> None:
    payload = UnifiedExecutionRequestBody(
        task_type="chat",
        user_input="hello",
        execution_policy={
            "preferred_profile_id": "local_ollama",
            "selection_mode": "preferred",
            "locality_preference": "local_only",
        },
    )

    request = payload.to_application_request()

    assert request.execution_policy.preferred_profile_id == "local_ollama"
    assert request.execution_policy.locality_preference.value == "local_only"


def test_unified_execution_request_supports_requested_skill_binding() -> None:
    payload = UnifiedExecutionRequestBody(
        task_type="chat",
        user_input="hello",
        requested_skill_id=" echo ",
        requested_skill_arguments={"text": "hello"},
        skill_policy={"mode": "allowlisted", "allowlist": ["echo"]},
    )

    request = payload.to_application_request()

    assert request.requested_skill_id == "echo"
    assert request.requested_skill_arguments == {"text": "hello"}
    assert request.skill_policy.allowed_skill_ids == ("echo",)


def test_runtime_profile_list_response_hides_secrets() -> None:
    response = RuntimeProfileListResponse.from_summaries(
        (
            RuntimeProfileSummary(
                profile_id="default_cloud",
                display_name="Default Cloud",
                provider_kind="openai_compatible",
                model_name="gpt-4o-mini",
                tags=("cloud",),
                enabled=True,
                capabilities=("supports_chat",),
            ),
        )
    )

    assert response.items[0].profile_id == "default_cloud"
    assert "api_key" not in response.model_dump_json().lower()


def test_citation_item_from_record_accepts_dataclass() -> None:
    citation = CitationItem.from_record(
        CitationRecord(doc_id="d1", chunk_id="c1", source="kb/doc.md", snippet="text")
    )
    assert citation.chunk_id == "c1"


def _item_to_entry(item: SourceCatalogItem) -> SourceCatalogEntry:
    return SourceCatalogEntry(
        doc_id=item.doc_id,
        source=item.source,
        source_type=item.source_type,
        title=item.title,
        chunk_count=item.chunk_count,
        sections=tuple(item.sections),
        pages=tuple(item.pages),
        requested_url=item.requested_url,
        final_url=item.final_url,
    )
